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

_connected = False  # estado de conexión MT5


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


# ─── Conexión MT5 ────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    login: int
    password: str
    server: str

@app.get("/api/connection")
def get_connection():
    info = mt5.account_info()
    if info:
        return {
            "connected": True,
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "currency": info.currency,
            "name": info.name,
        }
    return {"connected": False}


@app.post("/api/connect")
def connect_account(req: ConnectRequest):
    try:
        # Actualizar config en memoria
        config.MT5_LOGIN = req.login
        config.MT5_PASSWORD = req.password
        config.MT5_SERVER = req.server

        mt5.shutdown()
        if not mt5.initialize(path=config.MT5_PATH or None):
            return {"ok": False, "error": f"No se pudo inicializar MT5: {mt5.last_error()}"}

        authorized = mt5.login(login=req.login, password=req.password, server=req.server)
        if not authorized:
            return {"ok": False, "error": f"Login fallido: {mt5.last_error()}"}

        info = mt5.account_info()
        return {
            "ok": True,
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "currency": info.currency,
            "name": info.name,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/disconnect")
def disconnect_account():
    mt5.shutdown()
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

    state = db.get_today_state()
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
def get_report(days: int = 7):
    return db.performance_report(days_back=days)


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


# ─── Control del Bot ──────────────────────────────────────────────────────────

@app.get("/api/bot/state")
def get_bot_state():
    s = bot_state.get()
    return {
        "manual_mode": s["manual_mode"],
        "analysis_enabled": bot_state.is_analysis_active(),
        "trading_enabled": bot_state.is_trading_active(),
        "analysis_start": s["analysis_start"],
        "trading_start": s["trading_start"],
        "trading_end": s["trading_end"],
    }


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
    return {"ok": True, "manual_mode": False}


class HoursConfig(BaseModel):
    analysis_start: int
    trading_start: int
    trading_end: int


@app.post("/api/bot/hours")
def update_hours(req: HoursConfig):
    bot_state.set_hours(req.analysis_start, req.trading_start, req.trading_end)
    return {"ok": True, "analysis_start": req.analysis_start, "trading_start": req.trading_start, "trading_end": req.trading_end}
