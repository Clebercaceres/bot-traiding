"""
Todo lo que habla directo con el terminal MT5 vive acá.
Requiere que MT5 (terminal de escritorio) esté instalado y abierto en Windows,
con la cuenta demo ya logueada (o se loguea sola con los datos de config.py).
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import config

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
}


def connect():
    if not mt5.initialize(path=config.MT5_PATH or None):
        raise RuntimeError(f"No se pudo inicializar MT5: {mt5.last_error()}")

    # Solo intenta login si hay credenciales en config (pueden venir del dashboard)
    if config.MT5_LOGIN and config.MT5_PASSWORD and config.MT5_SERVER:
        authorized = mt5.login(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER,
        )
        if not authorized:
            raise RuntimeError(f"Login fallido (código {mt5.last_error()[0]}): credenciales incorrectas o servidor incorrecto.")

    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 inicializado pero sin cuenta activa. Conecta desde el dashboard.")
    print(f"[MT5] Conectado → cuenta {info.login} | balance: {info.balance} {info.currency}")
    return info


def disconnect():
    mt5.shutdown()


def get_account_balance():
    info = mt5.account_info()
    return info.balance if info else None


def get_candles(symbol, timeframe_str, count=300):
    tf = TIMEFRAME_MAP[timeframe_str]
    mt5.symbol_select(symbol, True)  # asegura que esté en Market Watch
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No se pudieron obtener velas de {symbol} en {timeframe_str}. "
                            f"¿El símbolo está visible en Market Watch? Error: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_symbol_info(symbol):
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar el símbolo {symbol} en Market Watch.")
    return mt5.symbol_info(symbol)


def get_current_price(symbol):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"Sin tick para {symbol}")
    return tick


def _get_filling_mode(symbol):
    """Detecta el modo de llenado soportado por el broker para este símbolo."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    fm = info.filling_mode
    if fm & 1:   # FOK
        return mt5.ORDER_FILLING_FOK
    if fm & 2:   # IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def place_market_order(symbol, direction, lot_size, sl, tp, comment="tradebot"):
    """direction: 'buy' | 'sell'. Devuelve el resultado de MT5."""
    tick = get_current_price(symbol)
    price = tick.ask if direction == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL

    # Recalcular SL/TP preservando las distancias originales pero ancladas al precio actual
    original_sl_dist = abs(sl - tp) / (config.ATR_SL_MULTIPLIER + config.ATR_TP_MULTIPLIER) * config.ATR_SL_MULTIPLIER
    original_tp_dist = abs(sl - tp) / (config.ATR_SL_MULTIPLIER + config.ATR_TP_MULTIPLIER) * config.ATR_TP_MULTIPLIER
    if direction == "buy":
        sl = price - original_sl_dist
        tp = price + original_tp_dist
    else:
        sl = price + original_sl_dist
        tp = price - original_tp_dist

    # Validar stop level mínimo del broker
    info = mt5.symbol_info(symbol)
    if info:
        min_stop = info.trade_stops_level * info.point
        sl_dist = abs(price - sl)
        tp_dist = abs(tp - price)
        if min_stop > 0:
            if sl_dist < min_stop * 1.2:
                sl = (price - min_stop * 2.0) if direction == "buy" else (price + min_stop * 2.0)
            if tp_dist < min_stop * 1.2:
                tp = (price + min_stop * 3.0) if direction == "buy" else (price - min_stop * 3.0)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 990011,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _get_filling_mode(symbol),
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Orden rechazada: {result.retcode} - {result.comment}")
    return result


def detect_broker() -> str:
    """Detecta el broker activo. Retorna 'bridge' | 'deriv' | 'unknown'."""
    info = mt5.account_info()
    if info is None:
        return "unknown"
    server = (info.server or "").lower()
    company = (info.company or "").lower()
    combined = server + company
    if "bridge" in combined:
        return "bridge"
    if "deriv" in combined or "binary" in combined:
        return "deriv"
    return "unknown"


def get_open_positions(magic=990011):
    positions = mt5.positions_get()
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]


def close_position(position):
    tick = get_current_price(position.symbol)
    order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": position.ticket,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": 990011,
        "comment": "tradebot-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _get_filling_mode(position.symbol),
    }
    return mt5.order_send(request)


def close_by_ticket(ticket: int):
    positions = mt5.positions_get(ticket=ticket)
    if positions:
        close_position(positions[0])


def is_connected() -> bool:
    return mt5.account_info() is not None and mt5.terminal_info() is not None


def get_balance_info() -> dict:
    info = mt5.account_info()
    if not info:
        return {"balance": 0, "currency": "USD"}
    return {"balance": info.balance, "currency": info.currency}
