"""Calcula lot_size sin depender de DB — el servidor maneja el estado."""
import config
import mt5_connector


def calculate_lot_size_simple(symbol: str, entry: float, sl: float) -> float:
    balance = mt5_connector.get_account_balance()
    if not balance:
        raise RuntimeError("Sin balance")
    risk_amount = balance * (config.RISK_PER_TRADE_PCT / 100.0)
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        raise ValueError("SL distance = 0")
    sym_info = mt5_connector.get_symbol_info(symbol)
    if not sym_info:
        raise RuntimeError(f"Sin info de {symbol}")
    tick_size  = sym_info.trade_tick_size
    tick_value = sym_info.trade_tick_value
    if tick_size == 0:
        raise ValueError("tick_size = 0")
    sl_ticks = sl_distance / tick_size
    sl_value_per_lot = sl_ticks * tick_value
    if sl_value_per_lot == 0:
        raise ValueError("sl_value_per_lot = 0")
    raw_lot = risk_amount / sl_value_per_lot
    min_lot = sym_info.volume_min
    max_lot = sym_info.volume_max
    step    = sym_info.volume_step
    lot = max(min_lot, min(max_lot, round(raw_lot // step * step, 8)))
    rr  = config.ATR_TP_MULTIPLIER / config.ATR_SL_MULTIPLIER
    print(f"[RISK] balance={balance:.2f} riesgo={risk_amount:.2f} ganancia_est={round(risk_amount*rr,2):.2f} lot={lot}")
    return lot
