"""
Dashboard web (FastAPI) en puerto config.DASHBOARD_PORT.
"""
import os
import MetaTrader5 as mt5
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
import db
import mt5_connector
import risk_manager
import push_service
import bot_state

app = FastAPI(title="TradeBot Dashboard")

_HTML_PATH = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")


# ─── HTML ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open(_HTML_PATH, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/sw.js")
def service_worker():
    from fastapi.responses import Response
    sw_path = os.path.join(os.path.dirname(__file__), "templates", "sw.js")
    with open(sw_path, encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/javascript")


# ─── Cuentas MT5 ─────────────────────────────────────────────────────────────

# Servidores conocidos para sugerir en la UI
KNOWN_SERVERS = [
    {"name": "BridgeMarkets-MT5", "broker": "bridge", "label": "Bridge Markets"},
    {"name": "Deriv-Demo",        "broker": "deriv",  "label": "Deriv Demo"},
    {"name": "Deriv-Server",      "broker": "deriv",  "label": "Deriv Real"},
]

class AccountRequest(BaseModel):
    login: int
    password: str
    server: str
    label: str = ""


@app.get("/api/accounts")
def list_accounts():
    rows = db.get_all_accounts()
    active_id = bot_state.get_active_account_id()
    result = []
    for r in rows:
        a = dict(r)
        a["active"] = (r["id"] == active_id)
        a.pop("password", None)  # nunca exponer password al frontend
        result.append(a)
    return result


@app.get("/api/accounts/servers")
def list_servers():
    return KNOWN_SERVERS


@app.post("/api/accounts")
def add_account(req: AccountRequest):
    """Guarda credenciales sin conectar todavía."""
    label = req.label.strip() or f"Cuenta {req.login}"
    account_id = db.save_account(
        login=req.login,
        password=req.password,
        server=req.server,
        label=label,
    )
    return {"ok": True, "account_id": account_id}


@app.post("/api/accounts/{account_id}/connect")
def connect_saved_account(account_id: int):
    """Conecta una cuenta guardada."""
    row = db.get_account(account_id)
    if not row:
        return {"ok": False, "error": "Cuenta no encontrada"}
    return _do_connect(row["login"], row["password"], row["server"], account_id)


@app.post("/api/connect")
def connect_account(req: AccountRequest):
    """Conecta y guarda la cuenta (flujo rápido desde panel de cuenta)."""
    label = req.label.strip() or f"Cuenta {req.login}"
    account_id = db.save_account(
        login=req.login,
        password=req.password,
        server=req.server,
        label=label,
    )
    return _do_connect(req.login, req.password, req.server, account_id)


def _do_connect(login: int, password: str, server: str, account_id: int):
    try:
        config.MT5_LOGIN = login
        config.MT5_PASSWORD = password
        config.MT5_SERVER = server

        mt5.shutdown()
        if not mt5.initialize(path=config.MT5_PATH or None):
            return {"ok": False, "error": f"No se pudo inicializar MT5: {mt5.last_error()}"}

        authorized = mt5.login(login=login, password=password, server=server)
        if not authorized:
            return {"ok": False, "error": f"Login fallido: {mt5.last_error()}"}

        info = mt5.account_info()
        broker = mt5_connector.detect_broker()

        # Actualizar balance y broker en DB
        db.save_account(login, password, server,
                        label=db.get_account(account_id)["label"],
                        broker=broker,
                        currency=info.currency)
        db.update_account_balance(account_id, info.balance, info.currency)
        db.activate_symbols_for_broker(broker)

        # Activar cuenta en bot_state
        bot_state.set_active_account(account_id)

        return {
            "ok": True,
            "account_id": account_id,
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "currency": info.currency,
            "name": info.name,
            "broker": broker,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: int):
    active = bot_state.get_active_account_id()
    if active == account_id:
        mt5.shutdown()
        bot_state.set_active_account(None)
    db.delete_account(account_id)
    return {"ok": True}


@app.get("/api/connection")
def get_connection():
    info = mt5.account_info()
    active_id = bot_state.get_active_account_id()
    if info:
        return {
            "connected": True,
            "account_id": active_id,
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "currency": info.currency,
            "name": info.name,
        }
    return {"connected": False, "account_id": None}


@app.post("/api/disconnect")
def disconnect_account():
    mt5.shutdown()
    bot_state.set_active_account(None)
    return {"ok": True}


@app.post("/api/db/reset")
def reset_db():
    """Limpia trades, señales y estado diario. Conserva cuentas y símbolos."""
    db.reset_db()
    return {"ok": True}


# ─── Señales y stats ─────────────────────────────────────────────────────────

@app.get("/api/pending")
def get_pending():
    rows = db.get_pending_signals()
    return [dict(r) for r in rows]


@app.post("/api/signal/{signal_id}/confirm")
def confirm_signal(signal_id: int):
    db.update_signal_status(signal_id, "confirmed")
    return {"ok": True, "signal_id": signal_id, "status": "confirmed"}


@app.post("/api/signal/{signal_id}/reject")
def reject_signal(signal_id: int):
    db.update_signal_status(signal_id, "rejected")
    return {"ok": True, "signal_id": signal_id, "status": "rejected"}


@app.get("/api/stats")
def get_stats():
    try:
        balance = mt5_connector.get_account_balance()
    except Exception:
        balance = None

    acct_id = bot_state.get_active_account_id()
    state = db.get_today_state(acct_id)
    can_trade = risk_manager.can_trade_today()

    return {
        "balance": balance,
        "trades_today": state["trades_count"],
        "max_trades": config.MAX_TRADES_PER_SESSION,
        "pnl_pct": round(state["pnl_pct"], 2),
        "active": can_trade,
        "stopped_reason": state["stopped_reason"],
        "consecutive_losses": state["consecutive_losses"],
    }


@app.get("/api/report")
def get_report(days: float = 7, date_from: str = None, date_to: str = None):
    acct_id = bot_state.get_active_account_id()
    return db.performance_report(days_back=days, date_from=date_from, date_to=date_to, account_id=acct_id)


@app.get("/api/signals/history")
def get_signals_history(limit: int = 50):
    acct_id = bot_state.get_active_account_id()
    return [dict(r) for r in db.get_signals_history(limit=limit, account_id=acct_id)]


# ─── Push Notifications ───────────────────────────────────────────────────────

class PushSubscription(BaseModel):
    endpoint: str
    p256dh: str
    auth: str

@app.get("/api/push/vapid-public-key")
def get_vapid_public_key():
    return {"publicKey": push_service.PUBLIC_KEY}

@app.post("/api/push/subscribe")
def push_subscribe(sub: PushSubscription):
    push_service.save_subscription(sub.endpoint, sub.p256dh, sub.auth)
    return {"ok": True}

@app.delete("/api/push/unsubscribe")
def push_unsubscribe(sub: PushSubscription):
    push_service.delete_subscription(sub.endpoint)
    return {"ok": True}


# ─── Símbolos ─────────────────────────────────────────────────────────────────

class SymbolAdd(BaseModel):
    name: str
    display_name: str
    category: str = "synthetic"

@app.get("/api/symbols")
def list_symbols():
    return [dict(r) for r in db.get_all_symbols()]

@app.get("/api/mt5-symbols")
def list_mt5_symbols(q: str = ""):
    syms = mt5.symbols_get()
    if not syms:
        return []
    result = []
    q_lower = q.lower()
    for s in syms:
        if not q_lower or q_lower in s.name.lower() or q_lower in s.description.lower():
            result.append({"name": s.name, "description": s.description, "category": s.path.split("\\")[0] if s.path else ""})
    return result[:80]


@app.post("/api/symbols")
def add_symbol(req: SymbolAdd):
    name = req.name.strip()
    mt5.symbol_select(name, True)
    info = mt5.symbol_info(name)
    if info is None:
        return {"ok": False, "error": f"'{name}' no encontrado en MT5."}
    db.add_symbol(name, req.display_name.strip() or info.description or name, req.category)
    return {"ok": True}

@app.post("/api/symbols/sync-market-watch")
def sync_market_watch():
    syms = mt5.symbols_get()
    if not syms:
        return {"ok": False, "error": "MT5 no conectado o sin símbolos"}
    added = 0
    for s in syms:
        if not s.visible:
            continue
        try:
            category = "synthetic"
            path = (s.path or "").lower()
            name_l = s.name.lower()
            if any(x in path or x in name_l for x in ["forex", "fx", "eurusd", "gbpusd"]):
                category = "forex"
            elif any(x in path or x in name_l for x in ["btc", "eth", "crypto"]):
                category = "crypto"
            elif any(x in path or x in name_l for x in ["gold", "xau", "oil", "silver"]):
                category = "commodity"
            elif any(x in path or x in name_l for x in ["us30", "nas", "spx", "dax"]):
                category = "cash"
            db.add_symbol(s.name, s.description or s.name, category)
            added += 1
        except Exception:
            pass
    return {"ok": True, "added": added}

@app.post("/api/symbols/{symbol_id}/toggle")
def toggle_symbol(symbol_id: int, active: bool = True):
    db.toggle_symbol(symbol_id, active)
    return {"ok": True}

@app.delete("/api/symbols/{symbol_id}")
def delete_symbol(symbol_id: int):
    db.delete_symbol(symbol_id)
    return {"ok": True}

@app.get("/api/symbols-context")
def get_symbols_context():
    try:
        from scheduler import _context_cache
        cache = _context_cache
    except Exception:
        cache = {}
    result = []
    try:
        rows = db.get_active_symbols()
    except Exception:
        return []
    for row in rows:
        sym = row["name"]
        ctx = cache.get(sym, {})
        result.append({
            "name": sym,
            "display_name": row["display_name"],
            "category": row["category"],
            "bias": ctx.get("bias", "sin datos"),
            "ema_fast": ctx.get("ema_fast"),
            "ema_slow": ctx.get("ema_slow"),
        })
    return result


# ─── Control del Bot ──────────────────────────────────────────────────────────

@app.get("/api/bot/state")
def get_bot_state():
    s = bot_state.get()
    return {
        "manual_mode": s["manual_mode"],
        "analysis_enabled": bot_state.is_analysis_active(),
        "trading_enabled": bot_state.is_trading_active(),
        "execution_auto": s.get("execution_auto", False),
    }


@app.post("/api/bot/execution/auto")
def set_exec_auto():
    bot_state.set_execution_auto(True)
    return {"ok": True, "execution_auto": True}


@app.post("/api/bot/execution/confirm")
def set_exec_confirm():
    bot_state.set_execution_auto(False)
    return {"ok": True, "execution_auto": False}


@app.post("/api/bot/analysis/start")
def start_analysis():
    bot_state.set_analysis(True)
    return {"ok": True, "analysis": True}


@app.post("/api/bot/analysis/stop")
def stop_analysis():
    bot_state.stop_all()
    return {"ok": True, "analysis": False, "trading": False}


@app.post("/api/bot/trading/start")
def start_trading():
    bot_state.set_trading(True)
    return {"ok": True, "trading": True}


@app.post("/api/bot/trading/stop")
def stop_trading():
    bot_state.set_trading(False)
    return {"ok": True, "trading": False}


@app.post("/api/bot/auto")
def set_auto_mode():
    bot_state.auto_mode()
    return {"ok": True}


class HoursConfig(BaseModel):
    analysis_start: int
    trading_start: int
    trading_end: int


@app.post("/api/bot/hours")
def update_hours(req: HoursConfig):
    bot_state.set_hours(req.analysis_start, req.trading_start, req.trading_end)
    return {"ok": True}
