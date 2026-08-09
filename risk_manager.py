"""
Gestión de riesgo:
  - Calcula lot_size basado en riesgo % del balance y distancia al SL
  - Controla pérdidas consecutivas y límite de pérdida diaria
  - Expone can_trade_today() para que el scheduler consulte antes de operar
"""
import config
import db
import mt5_connector
import push_service
import bot_state


def calculate_lot_size(symbol: str, entry: float, sl: float) -> float:
    """
    Calcula el tamaño de lote para arriesgar exactamente RISK_PER_TRADE_PCT del balance.
    Fórmula: lot = (balance * riesgo%) / (distancia_SL_en_pips * valor_pip)
    """
    balance = mt5_connector.get_account_balance()
    if not balance:
        raise RuntimeError("No se pudo obtener el balance de la cuenta.")

    risk_amount = balance * (config.RISK_PER_TRADE_PCT / 100.0)
    sl_distance = abs(entry - sl)

    if sl_distance == 0:
        raise ValueError("Distancia al SL es 0 — no se puede calcular lot_size.")

    sym_info = mt5_connector.get_symbol_info(symbol)
    if sym_info is None:
        raise RuntimeError(f"No se pudo obtener info del símbolo {symbol}")

    # tick_value = valor monetario de un tick (1 punto) por 1 lote
    tick_size = sym_info.trade_tick_size
    tick_value = sym_info.trade_tick_value

    if tick_size == 0:
        raise ValueError(f"tick_size=0 para {symbol}")

    # Cuántos ticks hay en la distancia al SL
    sl_ticks = sl_distance / tick_size

    # Valor monetario de la distancia SL por 1 lote
    sl_value_per_lot = sl_ticks * tick_value

    if sl_value_per_lot == 0:
        raise ValueError("sl_value_per_lot=0 — revisa los datos del símbolo.")

    raw_lot = risk_amount / sl_value_per_lot

    # Respetar mínimos y pasos del símbolo
    min_lot = sym_info.volume_min
    max_lot = sym_info.volume_max
    step = sym_info.volume_step

    # Redondear al step más cercano (hacia abajo para no exceder el riesgo)
    lot = max(min_lot, min(max_lot, round(raw_lot // step * step, 8)))

    # Ganancia potencial = riesgo * RR (más simple y correcto que calcular por ticks)
    rr = config.ATR_TP_MULTIPLIER / config.ATR_SL_MULTIPLIER
    potential_gain = round(risk_amount * rr, 2)

    print(f"[RISK] balance={balance:.2f} | riesgo={risk_amount:.2f} | ganancia_est={potential_gain:.2f} | SL_dist={sl_distance:.5f} | lot={lot}")
    return lot


def can_trade_today() -> bool:
    """Retorna True si la sesión sigue activa (no superó límites del día)."""
    acct_id = bot_state.get_active_account_id()
    state = db.get_today_state(acct_id)
    if state["stopped"]:
        print(f"[RISK] Sesión detenida: {state['stopped_reason']}")
        return False
    return True


def check_and_update_after_trade(profit: float, balance: float):
    acct_id = bot_state.get_active_account_id()
    state = db.get_today_state(acct_id)
    consecutive = state["consecutive_losses"]
    pnl_pct = state["pnl_pct"]

    # Actualizar PnL %
    if balance and balance > 0:
        pnl_delta = (profit / balance) * 100
        new_pnl_pct = pnl_pct + pnl_delta
    else:
        new_pnl_pct = pnl_pct

    # Actualizar pérdidas consecutivas
    if profit < 0:
        new_consecutive = consecutive + 1
    else:
        new_consecutive = 0  # se resetea con cualquier ganancia

    updates = {
        "consecutive_losses": new_consecutive,
        "pnl_pct": round(new_pnl_pct, 4),
    }

    # Verificar si hay que detener la sesión
    stopped = False
    reason = None

    if new_consecutive >= config.MAX_CONSECUTIVE_LOSSES:
        stopped = True
        reason = f"{new_consecutive} pérdidas consecutivas (límite: {config.MAX_CONSECUTIVE_LOSSES})"

    if new_pnl_pct <= -config.DAILY_LOSS_LIMIT_PCT:
        stopped = True
        reason = f"Pérdida diaria de {new_pnl_pct:.2f}% (límite: -{config.DAILY_LOSS_LIMIT_PCT}%)"

    if stopped:
        updates["stopped"] = 1
        updates["stopped_reason"] = reason
        print(f"[RISK] ⛔ SESIÓN DETENIDA: {reason}")
        push_service.notify_session_stopped(reason)

    db.update_today_state(account_id=acct_id, **updates)
    print(f"[RISK] Trade cerrado | profit={profit:.2f} | PnL día={new_pnl_pct:.2f}% | pérd.consec={new_consecutive}")
