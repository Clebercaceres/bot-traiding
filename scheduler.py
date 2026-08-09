"""
Loop principal del bot:
  - 3pm–8pm: solo análisis M15 cada 15 minutos
  - 8pm–12am: búsqueda de señales M1 cada minuto + monitoreo de posiciones
"""
import time
from datetime import datetime, date
import MetaTrader5 as mt5

import config
import db
import mt5_connector
import strategy
import risk_manager
import push_service
import bot_state

_last_m15_check: datetime | None = None
_context_cache: dict[str, dict] = {}   # symbol -> {bias, ema_fast, ema_slow}
_tracked_tickets: dict[int, dict] = {} # ticket -> {signal_id, open_price, open_time, symbol}


def _now_hour() -> float:
    now = datetime.now()
    return now.hour + now.minute / 60.0


def _in_analysis_window() -> bool:
    return bot_state.is_analysis_active()


def _in_trading_window() -> bool:
    return bot_state.is_trading_active()


def _trades_today() -> int:
    state = db.get_today_state()
    return state["trades_count"]


def _active_symbols() -> list[str]:
    try:
        rows = db.get_active_symbols()
        return [r["name"] for r in rows]
    except Exception:
        return []


def _maybe_refresh_m15():
    """Refresca contexto M15 de todos los símbolos activos cada 15 min."""
    global _last_m15_check
    now = datetime.now()
    if _last_m15_check and (now - _last_m15_check).seconds < 900:
        return
    for sym in _active_symbols():
        try:
            _context_cache[sym] = strategy.analyze_m15_context(sym)
        except Exception as e:
            print(f"[SCHEDULER] Error M15 {sym}: {e}")
    _last_m15_check = now


def _try_signal():
    """
    Escanea TODOS los símbolos activos, evalúa calidad de cada señal
    y ejecuta solo la de mayor score. Una señal por ciclo.
    """
    if not risk_manager.can_trade_today():
        return
    if _trades_today() >= config.MAX_TRADES_PER_SESSION:
        print(f"[SCHEDULER] Tope de sesión ({config.MAX_TRADES_PER_SESSION}) alcanzado.")
        return

    # Verificar límite de posiciones simultáneas
    open_positions = mt5_connector.get_open_positions()
    if len(open_positions) >= config.MAX_CONCURRENT_TRADES:
        return
    open_symbols = {p.symbol for p in open_positions}

    candidates = []  # lista de (score, signal, lot)

    for sym in _active_symbols():
        if sym in open_symbols:
            continue  # ya hay trade abierto en este símbolo
        ctx = _context_cache.get(sym)
        if not ctx or ctx.get("bias") == "neutral":
            continue
        try:
            signal = strategy.check_entry_signal(ctx)
        except Exception as e:
            print(f"[SCHEDULER] Error señal M1 {sym}: {e}")
            continue

        if signal is None:
            continue

        try:
            lot = risk_manager.calculate_lot_size(signal["symbol"], signal["entry"], signal["sl"])
        except Exception as e:
            print(f"[SCHEDULER] Error lot_size {sym}: {e}")
            continue

        score = signal.get("score", 0)
        candidates.append((score, signal, lot))

    if not candidates:
        return

    # Elegir la señal con mayor score de calidad
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_signal, best_lot = candidates[0]

    if best_score < config.MIN_SIGNAL_SCORE:
        print(f"[SCHEDULER] ⏭ Señal descartada (score={best_score} < mínimo={config.MIN_SIGNAL_SCORE})")
        return

    mode = "auto" if bot_state.get()["execution_auto"] else "confirm"
    print(f"[SCHEDULER] 🏆 Mejor señal: {best_signal['direction'].upper()} {best_signal['symbol']} | score={best_score} (de {len(candidates)} candidatos) | modo={mode}")

    signal_id = db.create_signal(
        symbol=best_signal["symbol"],
        direction=best_signal["direction"],
        entry_price=best_signal["entry"],
        sl=best_signal["sl"],
        tp=best_signal["tp"],
        lot_size=best_lot,
        rsi_value=best_signal["rsi"],
        score=best_score,
    )
    push_service.notify_signal(
        best_signal["symbol"], best_signal["direction"],
        best_signal["entry"], best_signal["sl"], best_signal["tp"]
    )

    # Modo automático: ejecutar directo sin esperar confirmación del dashboard
    if mode == "auto":
        _execute_signal_now(signal_id, best_signal, best_lot)


def _execute_signal_now(signal_id: int, signal: dict, lot: float):
    """Ejecuta una señal inmediatamente (modo automático)."""
    try:
        result = mt5_connector.place_market_order(
            symbol=signal["symbol"],
            direction=signal["direction"],
            lot_size=lot,
            sl=signal["sl"],
            tp=signal["tp"],
            comment=f"tradebot-{signal_id}",
        )
        ticket = result.order
        db.update_signal_status(signal_id, "executed", mt5_ticket=ticket)
        _tracked_tickets[ticket] = {
            "signal_id": signal_id,
            "open_price": result.price,
            "open_time": datetime.now().isoformat(),
            "symbol": signal["symbol"],
        }
        db.update_today_state(trades_count=_trades_today() + 1)
        print(f"[SCHEDULER] 🤖 Auto-ejecutado | ticket={ticket} | {signal['direction'].upper()} {signal['symbol']}")
        push_service.notify_trade_executed(signal["symbol"], signal["direction"], ticket, result.price)
    except Exception as e:
        print(f"[SCHEDULER] Error auto-ejecutando señal #{signal_id}: {e}")
        db.update_signal_status(signal_id, "failed")


def _execute_confirmed():
    """Ejecuta señales que el usuario confirmó en el dashboard (modo manual)."""
    confirmed = db.get_confirmed_signals()
    for sig in confirmed:
        try:
            result = mt5_connector.place_market_order(
                symbol=sig["symbol"],
                direction=sig["direction"],
                lot_size=sig["lot_size"],
                sl=sig["sl"],
                tp=sig["tp"],
                comment=f"tradebot-{sig['id']}",
            )
            ticket = result.order
            db.update_signal_status(sig["id"], "executed", mt5_ticket=ticket)
            _tracked_tickets[ticket] = {
                "signal_id": sig["id"],
                "open_price": result.price,
                "open_time": datetime.now().isoformat(),
                "symbol": sig["symbol"],
            }
            db.update_today_state(trades_count=_trades_today() + 1)
            print(f"[SCHEDULER] 🟢 Orden ejecutada | ticket={ticket} | {sig['direction'].upper()} {sig['symbol']}")
            push_service.notify_trade_executed(sig["symbol"], sig["direction"], ticket, result.price)
        except Exception as e:
            print(f"[SCHEDULER] Error ejecutando señal #{sig['id']}: {e}")
            db.update_signal_status(sig["id"], "rejected")


def _monitor_positions():
    """Detecta posiciones cerradas (por SL/TP o manualmente) y registra el resultado."""
    open_positions = mt5_connector.get_open_positions()
    open_tickets = {p.ticket for p in open_positions}

    closed = [t for t in list(_tracked_tickets.keys()) if t not in open_tickets]
    for ticket in closed:
        meta = _tracked_tickets.pop(ticket)
        try:
            # Buscar en historial de deals
            deals = mt5.history_deals_get(position=ticket)
            if not deals:
                print(f"[SCHEDULER] No se encontraron deals para ticket={ticket}")
                continue

            # El deal de cierre es el último (type != DEAL_TYPE_BUY entry)
            close_deal = None
            for d in reversed(deals):
                if d.entry == mt5.DEAL_ENTRY_OUT or d.entry == mt5.DEAL_ENTRY_INOUT:
                    close_deal = d
                    break

            if close_deal is None:
                print(f"[SCHEDULER] No se encontró deal de cierre para ticket={ticket}")
                continue

            profit = close_deal.profit
            close_price = close_deal.price
            close_time = datetime.fromtimestamp(close_deal.time).isoformat()

            result = db.record_trade_close(
                signal_id=meta["signal_id"],
                open_time=meta["open_time"],
                close_time=close_time,
                open_price=meta["open_price"],
                close_price=close_price,
                profit=profit,
            )

            balance = mt5_connector.get_account_balance()
            risk_manager.check_and_update_after_trade(profit, balance)

            icon = "✅" if result == "win" else "❌"
            print(f"[SCHEDULER] {icon} Trade cerrado | ticket={ticket} | profit={profit:.2f} | resultado={result}")
            push_service.notify_trade_closed(meta.get("symbol", "–"), profit, result)

        except Exception as e:
            print(f"[SCHEDULER] Error monitoreando ticket={ticket}: {e}")


def _manage_open_positions():
    """
    Gestión activa de posiciones abiertas:
    - Breakeven: cuando profit >= 50% del riesgo inicial, mueve SL a precio de entrada
    - Trailing stop: cuando profit >= 100% del riesgo inicial, arrastra SL a 50% del recorrido
    """
    open_positions = mt5_connector.get_open_positions()
    for pos in open_positions:
        if pos.ticket not in _tracked_tickets:
            continue
        try:
            entry = pos.price_open
            current_sl = pos.sl
            current_tp = pos.tp
            is_buy = pos.type == mt5.ORDER_TYPE_BUY

            sl_distance = abs(entry - current_sl) if current_sl else 0
            if sl_distance == 0:
                continue

            # Precio actual
            tick = mt5_connector.get_current_price(pos.symbol)
            current_price = tick.bid if is_buy else tick.ask
            sym_info = mt5.symbol_info(pos.symbol)
            point = sym_info.point if sym_info else 0.0001

            profit_distance = (current_price - entry) if is_buy else (entry - current_price)

            profit_pct = profit_distance / sl_distance if sl_distance > 0 else 0

            # Cierre anticipado por reversión o ganancia suficiente
            tp_distance = abs(current_tp - entry) if current_tp else 0
            if tp_distance > 0 and profit_distance > 0:
                tp_pct = profit_distance / tp_distance

                # Vela M1 más reciente va en contra de la posición
                try:
                    df_m1 = mt5_connector.get_candles(pos.symbol, "M1", count=3)
                    last_candle = df_m1.iloc[-2]  # vela cerrada más reciente
                    candle_bearish = last_candle["close"] < last_candle["open"]
                    candle_bullish = last_candle["close"] > last_candle["open"]
                    reversal = (is_buy and candle_bearish) or (not is_buy and candle_bullish)
                except Exception:
                    reversal = False

                # Cerrar si: ganancia >= 80% del TP sin importar vela
                # O ganancia >= 60% del TP Y hay vela de reversión
                should_close = (tp_pct >= 0.8) or (tp_pct >= 0.6 and reversal)

                if should_close:
                    reason = "80% TP alcanzado" if tp_pct >= 0.8 else "60% TP + vela reversión"
                    print(f"[SCHEDULER] 💰 Cierre anticipado ticket={pos.ticket} | {reason} | ganancia={tp_pct*100:.0f}% del TP")
                    mt5_connector.close_position(pos)
                    continue

            # Breakeven: profit >= 50% del SL → SL a entrada (cuenta real, proteger antes)
            if profit_pct >= 0.5:
                if is_buy and current_sl < entry:
                    new_sl = entry + point
                    _modify_sl(pos, new_sl, current_tp)
                elif not is_buy and current_sl > entry:
                    new_sl = entry - point
                    _modify_sl(pos, new_sl, current_tp)

            # Trailing nivel 1: profit >= 120% del SL → asegurar 30% del recorrido
            if profit_pct >= 1.2:
                trail_sl = (current_price - sl_distance * 0.7) if is_buy else (current_price + sl_distance * 0.7)
                if is_buy and trail_sl > current_sl:
                    _modify_sl(pos, trail_sl, current_tp)
                elif not is_buy and trail_sl < current_sl:
                    _modify_sl(pos, trail_sl, current_tp)

            # Trailing nivel 2: profit >= 200% del SL → asegurar 60% del recorrido
            if profit_pct >= 2.0:
                trail_sl = (current_price - sl_distance * 0.4) if is_buy else (current_price + sl_distance * 0.4)
                if is_buy and trail_sl > current_sl:
                    _modify_sl(pos, trail_sl, current_tp)
                elif not is_buy and trail_sl < current_sl:
                    _modify_sl(pos, trail_sl, current_tp)

        except Exception as e:
            print(f"[SCHEDULER] Error gestionando ticket={pos.ticket}: {e}")


def _modify_sl(pos, new_sl: float, tp: float):
    """Modifica el SL de una posición abierta, respetando stop level mínimo del broker."""
    sym_info = mt5.symbol_info(pos.symbol)
    if sym_info:
        min_stop = sym_info.trade_stops_level * sym_info.point
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick and min_stop > 0:
            is_buy = pos.type == mt5.ORDER_TYPE_BUY
            current_price = tick.bid if is_buy else tick.ask
            dist = abs(current_price - new_sl)
            if dist < min_stop:
                # SL demasiado cerca del precio actual — no enviar
                return
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "sl": round(new_sl, 5),
        "tp": tp,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[SCHEDULER] 🔒 SL ajustado | ticket={pos.ticket} | nuevo SL={new_sl:.5f}")
    else:
        retcode = result.retcode if result else "?"
        print(f"[SCHEDULER] Error ajustando SL ticket={pos.ticket}: {retcode}")


def _mt5_ok() -> bool:
    """True si hay cuenta MT5 activa."""
    import MetaTrader5 as mt5
    return mt5.account_info() is not None


def run():
    """Loop infinito del scheduler. Corre en un hilo secundario."""
    print("[SCHEDULER] Iniciando loop...")
    while True:
        try:
            if not _mt5_ok():
                time.sleep(15)
                continue

            if _in_analysis_window() or _in_trading_window():
                _maybe_refresh_m15()

            if _in_trading_window():
                _manage_open_positions()
                _try_signal()
                _execute_confirmed()
                _monitor_positions()
                time.sleep(60)
            elif _in_analysis_window():
                time.sleep(60)
            else:
                time.sleep(60)

        except Exception as e:
            print(f"[SCHEDULER] Error inesperado en loop: {e}")
            time.sleep(30)
