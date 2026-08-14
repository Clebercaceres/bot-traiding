"""
Servidor central TradeBot SaaS.
Deploy en Railway/Render. Maneja auth, dashboard, WebSocket con agentes.
"""
import os
import json
from datetime import datetime, date
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import init_db, get_db
from models import User, Account, Signal, Trade, DailyState
from crypto import encrypt as encrypt_field, decrypt as decrypt_field
from mt5_engine import MT5Engine
from mt5_connector import provision_account
import config
from auth import (
    hash_password, verify_password, create_token,
    get_current_user, get_current_user_ws,
)
import ws_manager

app = FastAPI(title="TradeBot SaaS")

_HTML_DIR = os.path.join(os.path.dirname(__file__), "templates")

# MT5 engines corriendo en servidor (Deriv + Bridge vía MetaApi)
_mt5_engines: dict[int, MT5Engine] = {}


@app.on_event("startup")
def startup():
    init_db()
    print("[SERVER] Base de datos lista.")


# ─── HTML pages ──────────────────────────────────────────────────────────────

def _html(name: str) -> str:
    with open(os.path.join(_HTML_DIR, name), encoding="utf-8") as f:
        return f.read()


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    token = request.cookies.get("tb_token")
    if token:
        from auth import decode_token
        if decode_token(token).get("sub"):
            return RedirectResponse("/dashboard")
    return HTMLResponse(_html("login.html"))


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return HTMLResponse(_html("register.html"))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    token = request.cookies.get("tb_token")
    if not token:
        return RedirectResponse("/")
    from auth import decode_token
    if not decode_token(token).get("sub"):
        return RedirectResponse("/")
    return HTMLResponse(_html("dashboard.html"))


# ─── Auth ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(400, "Email ya registrado")
    if len(req.password) < 6:
        raise HTTPException(400, "Contraseña mínimo 6 caracteres")
    user = User(
        email=req.email.lower().strip(),
        name=req.name.strip(),
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id, user.email)
    response = Response(content=json.dumps({"ok": True, "name": user.name}),
                        media_type="application/json")
    response.set_cookie("tb_token", token, httponly=True, samesite="lax", max_age=60*60*24*7)
    return response


@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Email o contraseña incorrectos")
    token = create_token(user.id, user.email)
    response = Response(
        content=json.dumps({"ok": True, "name": user.name}),
        media_type="application/json",
    )
    response.set_cookie("tb_token", token, httponly=True, samesite="lax", max_age=60*60*24*7)
    return response


@app.post("/api/auth/logout")
def logout():
    response = Response(content=json.dumps({"ok": True}), media_type="application/json")
    response.delete_cookie("tb_token")
    return response


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email}


# ─── Cuentas MT5 ─────────────────────────────────────────────────────────────

KNOWN_SERVERS = [
    {"name": "BridgeMarkets-MT5", "broker": "bridge", "label": "Bridge Markets"},
    {"name": "Deriv-Demo",        "broker": "deriv",  "label": "Deriv Demo"},
    {"name": "Deriv-Server",      "broker": "deriv",  "label": "Deriv Real"},
]

BRIDGE_SYMBOLS  = ["BullX500","BearX500","BullX777","BearX777","BullX1000","BearX1000"]
DERIV_SYMBOLS   = ["Volatility 75 Index","Volatility 100 Index"]


class AccountRequest(BaseModel):
    label: str
    login: int = 0
    password: str = ""
    server: str = ""
    api_token: str = ""   # Deriv: token directo (sin agente local)


@app.get("/api/accounts/servers")
def list_servers():
    return KNOWN_SERVERS


@app.get("/api/accounts")
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.user_id == user.id).all()
    return [
        {
            "id": a.id,
            "label": a.label,
            "login": a.login,
            "server": a.server,
            "broker": a.broker,
            "currency": a.currency,
            "balance": a.balance,
            "agent_online": ws_manager.is_online(a.id),
            "last_connected": a.last_connected.isoformat() if a.last_connected else None,
        }
        for a in accounts
    ]


@app.post("/api/accounts")
async def add_account(req: AccountRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = req.server.lower()
    broker = "bridge" if "bridge" in s else ("deriv" if "deriv" in s or "binary" in s else "unknown")
    if req.api_token:
        broker = "deriv"

    existing = db.query(Account).filter(Account.user_id == user.id, Account.login == req.login).first() if req.login else None
    if existing:
        existing.label     = req.label or existing.label
        existing.password  = encrypt_field(req.password) if req.password else existing.password
        existing.api_token = req.api_token or existing.api_token
        existing.server    = req.server or existing.server
        existing.broker    = broker
        db.commit()
        # Re-provisionar en MetaApi si no tiene metaapi_account_id aún
        if not existing.metaapi_account_id and config.METAAPI_TOKEN and req.password:
            try:
                maid = await provision_account(
                    config.METAAPI_TOKEN, existing.login,
                    req.password, existing.server, existing.label
                )
                existing.metaapi_account_id = maid
                db.commit()
            except Exception as e:
                print(f"[METAAPI] Provisioning error: {e}")
        return {"ok": True, "account_id": existing.id, "broker": broker}

    acct = Account(
        user_id   = user.id,
        label     = req.label or f"Cuenta {req.login or 'Deriv'}",
        login     = req.login or 0,
        password  = encrypt_field(req.password) if req.password else None,
        api_token = req.api_token or None,
        server    = req.server or "Deriv-API",
        broker    = broker,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)

    # Provisionar en MetaApi (Deriv + Bridge) si hay token configurado
    if req.password and config.METAAPI_TOKEN:
        try:
            maid = await provision_account(
                config.METAAPI_TOKEN, req.login,
                req.password, req.server, req.label
            )
            acct.metaapi_account_id = maid
            db.commit()
            print(f"[METAAPI] ✅ Cuenta {req.login} provisionada → {maid}")
        except Exception as e:
            print(f"[METAAPI] ⚠️ Provisioning error (puede completarse luego): {e}")
    db.refresh(acct)
    return {"ok": True, "account_id": acct.id, "broker": broker}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acct = db.query(Account).filter(Account.id == account_id, Account.user_id == user.id).first()
    if not acct:
        raise HTTPException(404, "Cuenta no encontrada")
    db.delete(acct)
    db.commit()
    return {"ok": True}


@app.post("/api/accounts/{account_id}/command")
async def send_command(
    account_id: int,
    command: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.query(Account).filter(Account.id == account_id, Account.user_id == user.id).first()
    if not acct:
        raise HTTPException(404, "Cuenta no encontrada")

    # MetaApi: Deriv + Bridge sin agente local
    if acct.metaapi_account_id and config.METAAPI_TOKEN:
        engine = _mt5_engines.get(account_id)
        if command in ("analysis_start", "trading_start"):
            if not engine:
                engine = MT5Engine(
                    account_id         = account_id,
                    metaapi_token      = config.METAAPI_TOKEN,
                    metaapi_account_id = acct.metaapi_account_id,
                    on_signal          = lambda sig: _on_signal(account_id, sig, db),
                    on_trade_closed    = lambda res: _on_closed(account_id, res, db),
                    on_balance         = lambda bal: _on_balance(account_id, bal, db),
                    auto_mode          = False,
                )
                _mt5_engines[account_id] = engine
                await engine.start()
            if command == "trading_start":
                engine.set_trading(True)
        elif command == "trading_stop":
            if engine:
                engine.set_trading(False)
        elif command == "stop":
            if engine:
                await engine.stop()
                _mt5_engines.pop(account_id, None)
        elif command == "set_auto":
            if engine:
                engine.set_auto(True)
        elif command == "set_confirm":
            if engine:
                engine.set_auto(False)
        return {"ok": True, "mode": "metaapi"}

    # Fallback: agente local vía WebSocket (para quien aún lo use)
    sent = await ws_manager.send_command(account_id, command)
    if not sent:
        if not config.METAAPI_TOKEN:
            raise HTTPException(503, "METAAPI_TOKEN no configurado en el servidor. Agrégalo en Render → Environment.")
        if not acct.metaapi_account_id:
            raise HTTPException(503, "Cuenta sin MetaApi ID. Borra la cuenta y agrégala de nuevo (el token ya debe estar en Render).")
        raise HTTPException(503, "Agente offline. Verifica que el bot local esté corriendo y conectado.")
    return {"ok": True}


# ── Callbacks unificados ──────────────────────────────────────────────────────

async def _on_signal(account_id: int, sig: dict, db):
    signal = Signal(
        account_id  = account_id,
        symbol      = sig["symbol"],
        direction   = sig["direction"],
        entry_price = sig.get("entry"),
        sl          = sig.get("sl"),
        tp          = sig.get("tp"),
        lot_size    = sig.get("lot"),
        rsi_value   = sig.get("rsi"),
        score       = sig.get("score"),
        status      = "pending",
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    if sig.get("auto"):
        signal.status = "confirmed"
        db.commit()
        engine = _mt5_engines.get(account_id)
        if engine:
            await engine.execute_signal(signal.id, sig)


async def _on_closed(account_id: int, res: dict, db):
    sig_id = res.get("signal_id")
    if sig_id and sig_id > 0:
        sig = db.query(Signal).filter(Signal.id == sig_id).first()
        if sig:
            sig.status = "closed"
            db.commit()


async def _on_balance(account_id: int, balance: float, db):
    acct = db.query(Account).filter(Account.id == account_id).first()
    if acct:
        acct.balance = balance
        db.commit()


# ─── Señales ─────────────────────────────────────────────────────────────────

@app.get("/api/signals/pending")
def pending_signals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account_ids = [a.id for a in db.query(Account).filter(Account.user_id == user.id).all()]
    sigs = db.query(Signal).filter(
        Signal.account_id.in_(account_ids),
        Signal.status == "pending"
    ).order_by(Signal.id.desc()).all()
    return [_signal_dict(s) for s in sigs]


@app.post("/api/signals/{signal_id}/confirm")
async def confirm_signal(signal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sig = _get_user_signal(signal_id, user, db)
    sig.status = "confirmed"
    db.commit()
    await ws_manager.send_command(sig.account_id, "execute_signal", signal_id=signal_id)
    return {"ok": True}


@app.post("/api/signals/{signal_id}/reject")
def reject_signal(signal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sig = _get_user_signal(signal_id, user, db)
    sig.status = "rejected"
    db.commit()
    return {"ok": True}


@app.get("/api/signals/history")
def signals_history(
    account_id: int = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account_ids = [a.id for a in db.query(Account).filter(Account.user_id == user.id).all()]
    q = db.query(Signal).filter(Signal.account_id.in_(account_ids))
    if account_id and account_id in account_ids:
        q = q.filter(Signal.account_id == account_id)
    sigs = q.order_by(Signal.id.desc()).limit(limit).all()
    return [_signal_dict(s) for s in sigs]


@app.get("/api/config/metaapi")
def metaapi_status():
    return {"configured": bool(config.METAAPI_TOKEN)}


@app.post("/api/accounts/{account_id}/sync-balance")
async def sync_balance(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fetch balance from MetaApi and update DB — no engine needed."""
    acct = db.query(Account).filter(Account.id == account_id, Account.user_id == user.id).first()
    if not acct:
        raise HTTPException(404, "Cuenta no encontrada")
    if not acct.metaapi_account_id or not config.METAAPI_TOKEN:
        raise HTTPException(503, "Cuenta sin MetaApi ID o token no configurado")
    engine = _mt5_engines.get(account_id)
    if engine:
        try:
            bal = await engine._conn.get_balance()
            acct.balance = bal
            db.commit()
            return {"balance": bal, "currency": acct.currency}
        except Exception:
            pass
    # Engine no activo — conexión rápida solo para leer balance
    from mt5_connector import MT5Connector
    conn = MT5Connector(config.METAAPI_TOKEN, acct.metaapi_account_id)
    try:
        info = await conn.connect()
        bal  = info.get("balance", 0.0)
        cur  = info.get("currency", "USD")
        acct.balance  = bal
        acct.currency = cur
        db.commit()
        return {"balance": bal, "currency": cur}
    except Exception as e:
        raise HTTPException(503, f"Error conectando MetaApi: {e}")
    finally:
        await conn.disconnect()


# ─── Stats y reporte ─────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(account_id: int = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acct = _get_account(account_id, user, db)
    if not acct:
        return {"balance": None, "trades_today": 0, "pnl_pct": 0, "consecutive_losses": 0, "stopped": False}
    today = date.today().isoformat()
    state = db.query(DailyState).filter(
        DailyState.account_id == acct.id, DailyState.day == today
    ).first()
    return {
        "balance": acct.balance,
        "currency": acct.currency,
        "trades_today": state.trades_count if state else 0,
        "pnl_pct": round(state.pnl_pct, 2) if state else 0,
        "consecutive_losses": state.consecutive_losses if state else 0,
        "stopped": state.stopped if state else False,
        "stopped_reason": state.stopped_reason if state else None,
        "agent_online": ws_manager.is_online(acct.id),
    }


@app.get("/api/report")
def get_report(
    account_id: int = None,
    days: float = 7,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = _get_account(account_id, user, db)
    if not acct:
        return {"summary": {}, "trades": [], "pnl_curve": [], "by_symbol": []}
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(hours=int(days * 24))
    trades = db.query(Trade).filter(
        Trade.account_id == acct.id,
        Trade.close_time >= since,
    ).order_by(Trade.close_time.desc()).all()
    wins   = [t for t in trades if t.result == "win"]
    losses = [t for t in trades if t.result == "loss"]
    total  = sum(t.profit or 0 for t in trades)
    pnl_curve = []
    acc = 0
    for t in reversed(trades):
        acc += t.profit or 0
        pnl_curve.append({"time": t.close_time.isoformat() if t.close_time else None, "pnl": round(acc, 2)})
    sym_stats = {}
    for t in trades:
        sig = t.signal
        sym = sig.symbol if sig else "—"
        if sym not in sym_stats:
            sym_stats[sym] = {"wins": 0, "losses": 0, "pnl": 0}
        sym_stats[sym]["wins" if t.result == "win" else "losses"] += 1
        sym_stats[sym]["pnl"] = round(sym_stats[sym]["pnl"] + (t.profit or 0), 2)
    return {
        "summary": {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "total_pnl": round(total, 2),
        },
        "pnl_curve": pnl_curve,
        "by_symbol": [{"symbol": k, **v} for k, v in sym_stats.items()],
        "trades": [_trade_dict(t) for t in trades],
    }


# ─── WebSocket — agente MT5 ───────────────────────────────────────────────────

@app.websocket("/ws/agent/{account_id}")
async def agent_ws(websocket: WebSocket, account_id: int, token: str = ""):
    db = next(get_db())
    user = get_current_user_ws(token, db)
    if not user:
        await websocket.close(code=4001)
        return

    acct = db.query(Account).filter(Account.id == account_id, Account.user_id == user.id).first()
    if not acct:
        await websocket.close(code=4004)
        return

    await ws_manager.connect(account_id, websocket)
    acct.agent_online = True
    acct.last_connected = datetime.utcnow()
    db.commit()

    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await _handle_agent_event(event, acct, db)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(account_id)
        acct.agent_online = False
        db.commit()
        db.close()


async def _handle_agent_event(event: dict, acct: Account, db: Session):
    etype = event.get("type")

    if etype == "balance_update":
        acct.balance  = event.get("balance", acct.balance)
        acct.currency = event.get("currency", acct.currency)
        db.commit()

    elif etype == "signal":
        sig = Signal(
            account_id  = acct.id,
            symbol      = event["symbol"],
            direction   = event["direction"],
            entry_price = event.get("entry"),
            sl          = event.get("sl"),
            tp          = event.get("tp"),
            lot_size    = event.get("lot_size"),
            rsi_value   = event.get("rsi"),
            score       = event.get("score"),
            status      = "pending",
        )
        db.add(sig)
        db.commit()
        db.refresh(sig)
        # Si modo auto, confirmar inmediatamente
        if event.get("auto"):
            sig.status = "confirmed"
            db.commit()
            await ws_manager.send_command(acct.id, "execute_signal", signal_id=sig.id)

    elif etype == "signal_executed":
        sig = db.query(Signal).filter(Signal.id == event.get("signal_id")).first()
        if sig:
            sig.status     = "executed"
            sig.mt5_ticket = event.get("ticket")
            db.commit()

    elif etype == "trade_closed":
        sig_id = event.get("signal_id")
        profit = event.get("profit", 0)
        trade = Trade(
            account_id  = acct.id,
            signal_id   = sig_id,
            open_time   = datetime.fromisoformat(event["open_time"])  if event.get("open_time")  else None,
            close_time  = datetime.fromisoformat(event["close_time"]) if event.get("close_time") else None,
            open_price  = event.get("open_price"),
            close_price = event.get("close_price"),
            profit      = profit,
            result      = "win" if profit > 0 else "loss",
        )
        db.add(trade)
        if sig_id:
            sig = db.query(Signal).filter(Signal.id == sig_id).first()
            if sig:
                sig.status = "closed"
        db.commit()
        _update_daily_state(acct.id, profit, acct.balance, db)

    elif etype == "daily_state":
        _upsert_daily_state(acct.id, event, db)


def _update_daily_state(account_id: int, profit: float, balance: float, db: Session):
    today = date.today().isoformat()
    state = db.query(DailyState).filter(
        DailyState.account_id == account_id, DailyState.day == today
    ).first()
    if not state:
        state = DailyState(account_id=account_id, day=today)
        db.add(state)
    pnl_delta = (profit / balance * 100) if balance else 0
    state.pnl_pct += pnl_delta
    if profit < 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0
    state.trades_count += 1
    db.commit()


def _upsert_daily_state(account_id: int, data: dict, db: Session):
    today = date.today().isoformat()
    state = db.query(DailyState).filter(
        DailyState.account_id == account_id, DailyState.day == today
    ).first()
    if not state:
        state = DailyState(account_id=account_id, day=today)
        db.add(state)
    for k, v in data.items():
        if hasattr(state, k) and k not in ("id", "account_id", "day"):
            setattr(state, k, v)
    db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_account(account_id: int | None, user: User, db: Session) -> Account | None:
    q = db.query(Account).filter(Account.user_id == user.id)
    if account_id:
        return q.filter(Account.id == account_id).first()
    return q.order_by(Account.last_connected.desc()).first()


def _get_user_signal(signal_id: int, user: User, db: Session) -> Signal:
    account_ids = [a.id for a in db.query(Account).filter(Account.user_id == user.id).all()]
    sig = db.query(Signal).filter(Signal.id == signal_id, Signal.account_id.in_(account_ids)).first()
    if not sig:
        raise HTTPException(404, "Señal no encontrada")
    return sig


def _signal_dict(s: Signal) -> dict:
    return {
        "id": s.id,
        "account_id": s.account_id,
        "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        "symbol": s.symbol,
        "direction": s.direction,
        "entry_price": s.entry_price,
        "sl": s.sl,
        "tp": s.tp,
        "lot_size": s.lot_size,
        "rsi_value": s.rsi_value,
        "score": s.score,
        "status": s.status,
        "mt5_ticket": s.mt5_ticket,
    }


def _trade_dict(t: Trade) -> dict:
    sig = t.signal
    return {
        "id": t.id,
        "symbol": sig.symbol if sig else "—",
        "direction": sig.direction if sig else "—",
        "open_time": t.open_time.isoformat() if t.open_time else None,
        "close_time": t.close_time.isoformat() if t.close_time else None,
        "open_price": t.open_price,
        "close_price": t.close_price,
        "profit": t.profit,
        "result": t.result,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
