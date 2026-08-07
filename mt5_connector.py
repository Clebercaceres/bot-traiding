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

    if config.MT5_LOGIN:
        authorized = mt5.login(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER,
        )
        if not authorized:
            raise RuntimeError(f"Login fallido: {mt5.last_error()}")

    info = mt5.account_info()
    if info is None:
        raise RuntimeError("No hay cuenta conectada en MT5. Abre el terminal y loguea la cuenta demo.")
    print(f"[MT5] Conectado -> cuenta {info.login} | balance: {info.balance} {info.currency}")
    return info


def disconnect():
    mt5.shutdown()


def get_account_balance():
    info = mt5.account_info()
    return info.balance if info else None


def get_candles(symbol, timeframe_str, count=300):
    tf = TIMEFRAME_MAP[timeframe_str]
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


def place_market_order(symbol, direction, lot_size, sl, tp, comment="tradebot"):
    """direction: 'buy' | 'sell'. Devuelve el resultado de MT5."""
    tick = get_current_price(symbol)
    price = tick.ask if direction == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL

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
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Orden rechazada: {result.retcode} - {result.comment}")
    return result


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
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    return mt5.order_send(request)
