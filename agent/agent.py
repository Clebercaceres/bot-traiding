"""
Agente local TradeBot — corre en PC Windows con MT5.
Se conecta al servidor central vía WebSocket, recibe comandos y envía eventos.
"""
import asyncio
import json
import time
import threading
import requests
import websockets
from datetime import datetime

import config
import mt5_connector
import strategy
import risk_manager

# ── Estado del agente ─────────────────────────────────────────────────────────
_state = {
    "analysis_enabled": False,
    "trading_enabled": False,
    "execution_auto": False,
    "active_symbols": [],
}
_context_cache: dict = {}
_tracked_tickets: dict = {}
_token: str = ""
_ws = None


# ── Login en servidor central ─────────────────────────────────────────────────

def login_server() -> str:
    """Obtiene JWT del servidor. Retorna el token."""
    r = requests.post(
        f"{config.SERVER_URL}/api/auth/login",
        json={"email": config.TB_EMAIL, "password": config.TB_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    # El token viene en cookie — extraerlo
    cookie = r.cookies.get("tb_token")
    if not cookie:
        raise RuntimeError("No se recibió token del servidor")
    return cookie


# ── WebSocket loop ─────────────────────────────────────────────────────────────

async def ws_loop():
    global _token, _ws
    uri = f"{config.WS_URL}/ws/agent/{config.ACCOUNT_ID}?token={_token}"
    print(f"[AGENT] Conectando a servidor: {uri[:40]}...")

    async with websockets.connect(uri) as ws:
        _ws = ws
        print("[AGENT] Conectado al servidor central.")

        # Enviar balance inicial
        await send_event("balance_update", **mt5_connector.get_balance_info())

        # Loop: recibir comandos del servidor
        async for raw in ws:
            try:
                msg = json.loads(raw)
                await handle_command(msg)
            except Exception as e:
                print(f"[AGENT] Error procesando comando: {e}")


async def handle_command(msg: dict):
    cmd = msg.get("command")
    print(f"[AGENT] Comando recibido: {cmd}")

    if cmd == "analysis_start":
        _state["analysis_enabled"] = True
        print("[AGENT] Análisis M15 activado.")

    elif cmd == "analysis_stop":
        _state["analysis_enabled"] = False
        _state["trading_enabled"]  = False
        print("[AGENT] Análisis detenido.")

    elif cmd == "trading_start":
        _state["analysis_enabled"] = True
        _state["trading_enabled"]  = True
        print("[AGENT] Trading M1 activado.")

    elif cmd == "trading_stop":
        _state["trading_enabled"] = False
        print("[AGENT] Trading pausado.")

    elif cmd == "set_auto":
        _state["execution_auto"] = msg.get("auto", False)
        print(f"[AGENT] Modo ejecución: {'auto' if _state['execution_auto'] else 'confirmar'}")

    elif cmd == "set_symbols":
        _state["active_symbols"] = msg.get("symbols", [])
        print(f"[AGENT] Símbolos activos: {_state['active_symbols']}")

    elif cmd == "execute_signal":
        signal_id = msg.get("signal_id")
        await execute_signal_by_id(signal_id)

    elif cmd == "close_position":
        ticket = msg.get("ticket")
        mt5_connector.close_by_ticket(ticket)


async def send_event(event_type: str, **kwargs):
    global _ws
    if _ws:
        payload = {"type": event_type, "ts": datetime.utcnow().isoformat(), **kwargs}
        try:
            await _ws.send(json.dumps(payload))
        except Exception as e:
            print(f"[AGENT] Error enviando evento: {e}")


# ── Señales pendientes en memoria (para ejecutar cuando llegue confirm) ────────
_pending_signals: dict[int, dict] = {}


async def execute_signal_by_id(signal_id: int):
    sig = _pending_signals.get(signal_id)
    if not sig:
        print(f"[AGENT] Signal #{signal_id} no encontrada en memoria")
        return
    try:
        result = mt5_connector.place_market_order(
            symbol=sig["symbol"],
            direction=sig["direction"],
            lot_size=sig["lot_size"],
            sl=sig["sl"],
            tp=sig["tp"],
            comment=f"tb-{signal_id}",
        )
        ticket = result.order
        _tracked_tickets[ticket] = {
            "signal_id": signal_id,
            "open_price": result.price,
            "open_time": datetime.utcnow().isoformat(),
            "symbol": sig["symbol"],
        }
        await send_event("signal_executed", signal_id=signal_id, ticket=ticket, price=result.price)
        print(f"[AGENT] ✅ Ejecutado ticket={ticket}")
    except Exception as e:
        print(f"[AGENT] Error ejecutando señal: {e}")
        await send_event("signal_failed", signal_id=signal_id, error=str(e))


# ── Scheduler local (hilo secundario) ────────────────────────────────────────

_last_m15: datetime | None = None
_loop: asyncio.AbstractEventLoop | None = None


def run_scheduler():
    """Corre en hilo separado. Lee M15, busca señales M1, monitorea posiciones."""
    global _last_m15
    print("[SCHEDULER] Loop iniciado.")
    time.sleep(5)

    while True:
        try:
            if not mt5_connector.is_connected():
                time.sleep(15)
                continue

            # Detectar símbolos activos según broker
            if not _state["active_symbols"]:
                broker = mt5_connector.detect_broker()
                _state["active_symbols"] = (
                    ["BullX500","BearX500","BullX777","BearX777","BullX1000","BearX1000"]
                    if broker == "bridge" else
                    ["Volatility 75 Index","Volatility 100 Index"]
                )

            # M15 cada 15 min
            if _state["analysis_enabled"] or _state["trading_enabled"]:
                now = datetime.utcnow()
                if not _last_m15 or (now - _last_m15).seconds >= 900:
                    for sym in _state["active_symbols"]:
                        try:
                            _context_cache[sym] = strategy.analyze_m15_context(sym)
                        except Exception as e:
                            if "Call failed" not in str(e):
                                print(f"[SCHEDULER] Error M15 {sym}: {e}")
                    _last_m15 = now
                    # Enviar balance actualizado
                    info = mt5_connector.get_balance_info()
                    if _loop:
                        asyncio.run_coroutine_threadsafe(
                            send_event("balance_update", **info), _loop
                        )

            # M1 — buscar señales y monitorear
            if _state["trading_enabled"]:
                _try_signal()
                _monitor_positions()

            time.sleep(60)

        except Exception as e:
            print(f"[SCHEDULER] Error: {e}")
            time.sleep(30)


def _try_signal():
    open_positions = mt5_connector.get_open_positions()
    if len(open_positions) >= config.MAX_CONCURRENT_TRADES:
        return
    open_symbols = {p.symbol for p in open_positions}
    candidates = []

    for sym in _state["active_symbols"]:
        if sym in open_symbols:
            continue
        ctx = _context_cache.get(sym)
        if not ctx or ctx.get("bias") == "neutral":
            continue
        try:
            signal = strategy.check_entry_signal(ctx)
        except Exception:
            continue
        if signal is None:
            continue
        try:
            lot = risk_manager.calculate_lot_size_simple(sym, signal["entry"], signal["sl"])
        except Exception:
            continue
        candidates.append((signal.get("score", 0), signal, lot))

    if not candidates:
        return
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_signal, best_lot = candidates[0]

    if best_score < config.MIN_SIGNAL_SCORE:
        return

    # Generar ID local temporal y guardar en memoria
    import random
    local_id = random.randint(100000, 999999)
    _pending_signals[local_id] = {**best_signal, "lot_size": best_lot}

    mode = "auto" if _state["execution_auto"] else "confirm"
    print(f"[SCHEDULER] 🏆 {best_signal['direction'].upper()} {best_signal['symbol']} score={best_score} modo={mode}")

    # Enviar señal al servidor
    if _loop:
        asyncio.run_coroutine_threadsafe(
            send_event(
                "signal",
                signal_id=local_id,
                symbol=best_signal["symbol"],
                direction=best_signal["direction"],
                entry=best_signal["entry"],
                sl=best_signal["sl"],
                tp=best_signal["tp"],
                lot_size=best_lot,
                rsi=best_signal.get("rsi"),
                score=best_score,
                auto=_state["execution_auto"],
            ),
            _loop,
        )


def _monitor_positions():
    import MetaTrader5 as mt5
    open_positions = mt5_connector.get_open_positions()
    open_tickets   = {p.ticket for p in open_positions}
    closed = [t for t in list(_tracked_tickets.keys()) if t not in open_tickets]

    for ticket in closed:
        meta = _tracked_tickets.pop(ticket)
        try:
            deals = mt5.history_deals_get(position=ticket)
            if not deals:
                continue
            close_deal = None
            for d in reversed(deals):
                if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
                    close_deal = d
                    break
            if not close_deal:
                continue
            profit = close_deal.profit
            if _loop:
                asyncio.run_coroutine_threadsafe(
                    send_event(
                        "trade_closed",
                        signal_id=meta["signal_id"],
                        ticket=ticket,
                        open_time=meta["open_time"],
                        close_time=datetime.fromtimestamp(close_deal.time).isoformat(),
                        open_price=meta["open_price"],
                        close_price=close_deal.price,
                        profit=profit,
                    ),
                    _loop,
                )
            icon = "✅" if profit > 0 else "❌"
            print(f"[SCHEDULER] {icon} Trade cerrado ticket={ticket} profit={profit:.2f}")
        except Exception as e:
            print(f"[SCHEDULER] Error monitoreando {ticket}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global _token, _loop
    _loop = asyncio.get_event_loop()

    # 1. Conectar MT5
    try:
        mt5_connector.connect()
        print(f"[AGENT] MT5 conectado.")
    except Exception as e:
        print(f"[AGENT] Error MT5: {e}")
        return

    # 2. Login en servidor
    print("[AGENT] Autenticando en servidor...")
    _token = login_server()
    print("[AGENT] Autenticado.")

    # 3. Scheduler en hilo separado
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()

    # 4. WebSocket con reconexión automática
    while True:
        try:
            await ws_loop()
        except Exception as e:
            print(f"[AGENT] WebSocket desconectado: {e}. Reconectando en 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
