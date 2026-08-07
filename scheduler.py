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

_last_m15_check = None
_context_cache = {"bias": "neutral", "symbol": config.SYMBOL_BULL}
_tracked_tickets: dict[int, dict] = {}  # ticket -> {signal_id, open_price, open_time}


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


def _maybe_refresh_m15():
    global _last_m15_check, _context_cache
    now = datetime.now()
    if _last_m15_check is None or (now - _last_m15_check).seconds >= 900:
        try:
            _context_cache = strategy.analyze_m15_context()
        except Exception as e:
            print(f"[SCHEDULER] Error al analizar M15: {e}")
        _last_m15_check = now


def _try_signal():
    """Intenta detectar señal M1 y crearla en DB si hay."""
    if not risk_manager.can_trade_today():
        return

    if _trades_today() >= config.MAX_TRADES_PER_SESSION:
        print(f"[SCHEDULER] Tope de {config.MAX_TRADES_PER_SESSION} señales/sesión alcanzado.")
        return

    try:
        signal = strategy.check_entry_signal(_context_cache)
    except Exception as e:
        print(f"[SCHEDULER] Error al evaluar señal M1: {e}")
        return

    if signal is None:
        return

    try:
        lot = risk_manager.calculate_lot_size(signal["symbol"], signal["entry"], signal["sl"])
    except Exception as e:
        print(f"[SCHEDULER] Error calculando lot_size: {e}")
        return

    signal_id = db.create_signal(
        symbol=signal["symbol"],
        direction=signal["direction"],
        entry_price=signal["entry"],
        sl=signal["sl"],
        tp=signal["tp"],
        lot_size=lot,
        rsi_value=signal["rsi"],
    )
    print(f"[SCHEDULER] ✅ Señal #{signal_id} creada → pendiente de confirmación en dashboard")
    push_service.notify_signal(signal["symbol"], signal["direction"], signal["entry"], signal["sl"], signal["tp"])


def _execute_confirmed():
    """Ejecuta señales que el usuario confirmó en el dashboard."""
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


def run():
    """Loop infinito del scheduler. Corre en un hilo secundario."""
    print("[SCHEDULER] Iniciando loop...")
    while True:
        try:
            if _in_analysis_window() or _in_trading_window():
                _maybe_refresh_m15()

            if _in_trading_window():
                _try_signal()
                _execute_confirmed()
                _monitor_positions()
                time.sleep(60)
            elif _in_analysis_window():
                time.sleep(60)
            else:
                h = _now_hour()
                print(f"[SCHEDULER] Fuera de horario ({h:.1f}h). Durmiendo 60s...")
                time.sleep(60)

        except Exception as e:
            print(f"[SCHEDULER] Error inesperado en loop: {e}")
            time.sleep(30)
