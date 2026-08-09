"""
Base de datos local (SQLite). Guarda cuentas MT5, señales y trades.
Cada cuenta tiene su propio historial aislado.
"""
import sqlite3
from datetime import datetime, date
from contextlib import contextmanager
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    login INTEGER NOT NULL UNIQUE,
    password TEXT NOT NULL,
    server TEXT NOT NULL,
    broker TEXT DEFAULT 'unknown',
    currency TEXT DEFAULT 'USD',
    balance REAL DEFAULT 0,
    last_connected TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    category TEXT DEFAULT 'synthetic',
    active INTEGER DEFAULT 1,
    added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT,
    ema_fast REAL,
    ema_slow REAL,
    bias TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL,
    sl REAL,
    tp REAL,
    lot_size REAL,
    rsi_value REAL,
    score REAL,
    status TEXT DEFAULT 'pending',
    mt5_ticket INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),
    signal_id INTEGER,
    open_time TEXT,
    close_time TEXT,
    open_price REAL,
    close_price REAL,
    profit REAL,
    result TEXT,
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS daily_state (
    day TEXT NOT NULL,
    account_id INTEGER NOT NULL DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,
    pnl_pct REAL DEFAULT 0,
    stopped INTEGER DEFAULT 0,
    stopped_reason TEXT,
    PRIMARY KEY (day, account_id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    _seed_symbols()


def reset_db():
    """Borra todos los datos históricos. Conserva cuentas y símbolos."""
    with get_conn() as conn:
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM signals")
        conn.execute("DELETE FROM analysis_log")
        conn.execute("DELETE FROM daily_state")


# ── Cuentas ──────────────────────────────────────────────────────────────────

def get_all_accounts():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts ORDER BY last_connected DESC").fetchall()


def get_account(account_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()


def get_account_by_login(login: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts WHERE login=?", (login,)).fetchone()


def save_account(login: int, password: str, server: str, label: str, broker: str = "unknown", currency: str = "USD"):
    """Inserta o actualiza una cuenta. Retorna su id."""
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM accounts WHERE login=?", (login,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE accounts SET password=?, server=?, label=?, broker=?, currency=? WHERE login=?",
                (password, server, label, broker, currency, login),
            )
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO accounts (login, password, server, label, broker, currency) VALUES (?,?,?,?,?,?)",
            (login, password, server, label, broker, currency),
        )
        return cur.lastrowid


def update_account_balance(account_id: int, balance: float, currency: str = None):
    with get_conn() as conn:
        if currency:
            conn.execute(
                "UPDATE accounts SET balance=?, currency=?, last_connected=? WHERE id=?",
                (balance, currency, datetime.now().isoformat(), account_id),
            )
        else:
            conn.execute(
                "UPDATE accounts SET balance=?, last_connected=? WHERE id=?",
                (balance, datetime.now().isoformat(), account_id),
            )


def delete_account(account_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM trades WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM signals WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))


# ── Símbolos ──────────────────────────────────────────────────────────────────

def _seed_symbols():
    defaults = [
        ("BullX500",   "Bull X500",    "synthetic"),
        ("BearX500",   "Bear X500",    "synthetic"),
        ("BullX777",   "Bull X777",    "synthetic"),
        ("BearX777",   "Bear X777",    "synthetic"),
        ("BullX1000",  "Bull X1000",   "synthetic"),
        ("BearX1000",  "Bear X1000",   "synthetic"),
        ("Crash300N",  "Crash 300",    "synthetic"),
        ("Crash500",   "Crash 500",    "synthetic"),
        ("Crash1000",  "Crash 1000",   "synthetic"),
        ("Boom300N",   "Boom 300",     "synthetic"),
        ("Boom500",    "Boom 500",     "synthetic"),
        ("Boom1000",   "Boom 1000",    "synthetic"),
        ("Volatility 10 Index",  "Volatility 10",  "synthetic"),
        ("Volatility 25 Index",  "Volatility 25",  "synthetic"),
        ("Volatility 50 Index",  "Volatility 50",  "synthetic"),
        ("Volatility 75 Index",  "Volatility 75",  "synthetic"),
        ("Volatility 100 Index", "Volatility 100", "synthetic"),
    ]
    with get_conn() as conn:
        for name, display, cat in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO symbols (name, display_name, category, active) VALUES (?,?,?,0)",
                (name, display, cat),
            )
        conn.execute("UPDATE symbols SET active=1 WHERE name IN ('BullX500','BearX500')")


def activate_symbols_for_broker(broker: str):
    bridge_symbols = ("BullX500", "BearX500", "BullX777", "BearX777", "BullX1000", "BearX1000")
    deriv_symbols  = ("Volatility 75 Index", "Volatility 100 Index")
    with get_conn() as conn:
        conn.execute("UPDATE symbols SET active=0")
        if broker == "bridge":
            ph = ",".join("?" * len(bridge_symbols))
            conn.execute(f"UPDATE symbols SET active=1 WHERE name IN ({ph})", bridge_symbols)
            print(f"[DB] Broker=Bridge → {', '.join(bridge_symbols)}")
        elif broker == "deriv":
            ph = ",".join("?" * len(deriv_symbols))
            conn.execute(f"UPDATE symbols SET active=1 WHERE name IN ({ph})", deriv_symbols)
            print(f"[DB] Broker=Deriv → {', '.join(deriv_symbols)}")
        else:
            conn.execute("UPDATE symbols SET active=1 WHERE name IN ('BullX500','BearX500')")
            print("[DB] Broker desconocido → fallback BullX500+BearX500")


def log_analysis(symbol, ema_fast, ema_slow, bias):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analysis_log (timestamp, symbol, ema_fast, ema_slow, bias) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), symbol, ema_fast, ema_slow, bias),
        )


def get_active_symbols():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM symbols WHERE active=1 ORDER BY id").fetchall()


def get_all_symbols():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM symbols ORDER BY active DESC, id").fetchall()


def add_symbol(name, display_name, category="synthetic"):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO symbols (name, display_name, category) VALUES (?,?,?)",
            (name, display_name, category),
        )


def toggle_symbol(symbol_id, active):
    with get_conn() as conn:
        conn.execute("UPDATE symbols SET active=? WHERE id=?", (1 if active else 0, symbol_id))


def delete_symbol(symbol_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM symbols WHERE id=?", (symbol_id,))


# ── Señales ──────────────────────────────────────────────────────────────────

def create_signal(symbol, direction, entry_price, sl, tp, lot_size, rsi_value, score=None, account_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (account_id, timestamp, symbol, direction, entry_price, sl, tp, lot_size, rsi_value, score, status)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'pending')""",
            (account_id, datetime.now().isoformat(), symbol, direction, entry_price, sl, tp, lot_size, rsi_value, score),
        )
        return cur.lastrowid


def update_signal_status(signal_id, status, mt5_ticket=None):
    with get_conn() as conn:
        if mt5_ticket is not None:
            conn.execute("UPDATE signals SET status=?, mt5_ticket=? WHERE id=?",
                         (status, mt5_ticket, signal_id))
        else:
            conn.execute("UPDATE signals SET status=? WHERE id=?", (status, signal_id))


def get_pending_signals():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM signals WHERE status='pending' ORDER BY id DESC").fetchall()


def get_confirmed_signals():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM signals WHERE status='confirmed' ORDER BY id").fetchall()


def get_signals_history(limit: int = 50, account_id: int = None):
    with get_conn() as conn:
        if account_id:
            return conn.execute(
                "SELECT * FROM signals WHERE account_id=? ORDER BY id DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
        return conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ── Trades ───────────────────────────────────────────────────────────────────

def record_trade_close(signal_id, open_time, close_time, open_price, close_price, profit, account_id=None):
    result = "win" if profit > 0 else "loss"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO trades (account_id, signal_id, open_time, close_time, open_price, close_price, profit, result)
               VALUES (?,?,?,?,?,?,?,?)""",
            (account_id, signal_id, open_time, close_time, open_price, close_price, profit, result),
        )
        conn.execute("UPDATE signals SET status='closed' WHERE id=?", (signal_id,))
    return result


# ── Estado diario ─────────────────────────────────────────────────────────────

def get_today_state(account_id: int = None):
    today = date.today().isoformat()
    aid = account_id or 0
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO daily_state (day, account_id) VALUES (?,?)",
            (today, aid),
        )
        return conn.execute(
            "SELECT * FROM daily_state WHERE day=? AND account_id=?", (today, aid)
        ).fetchone()


def update_today_state(account_id: int = None, **fields):
    today = date.today().isoformat()
    aid = account_id or 0
    get_today_state(aid)
    sets = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE daily_state SET {sets} WHERE day=? AND account_id=?",
            list(fields.values()) + [today, aid],
        )


# ── Reporte de rendimiento ────────────────────────────────────────────────────

def performance_report(days_back: float = 7, date_from: str = None, date_to: str = None, account_id: int = None):
    with get_conn() as conn:
        acc_filter = "AND t.account_id=?" if account_id else ""
        acc_val = (account_id,) if account_id else ()

        if date_from and date_to:
            trades = conn.execute(
                f"SELECT t.*, s.symbol, s.direction FROM trades t "
                f"LEFT JOIN signals s ON t.signal_id = s.id "
                f"WHERE date(t.close_time) BETWEEN ? AND ? {acc_filter} ORDER BY t.close_time DESC",
                (date_from, date_to) + acc_val,
            ).fetchall()
            daily = conn.execute(
                f"SELECT * FROM daily_state WHERE day BETWEEN ? AND ? "
                + ("AND account_id=? " if account_id else "")
                + "ORDER BY day",
                (date_from, date_to) + acc_val,
            ).fetchall()
        else:
            hours = int(days_back * 24)
            trades = conn.execute(
                f"SELECT t.*, s.symbol, s.direction FROM trades t "
                f"LEFT JOIN signals s ON t.signal_id = s.id "
                f"WHERE t.close_time >= datetime('now', '-{hours} hours') {acc_filter} ORDER BY t.close_time DESC",
                acc_val,
            ).fetchall()
            daily = conn.execute(
                f"SELECT * FROM daily_state WHERE day >= date('now', '-{int(days_back)} days') "
                + ("AND account_id=? " if account_id else "")
                + "ORDER BY day",
                acc_val,
            ).fetchall()

    wins   = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    total_profit = sum(t["profit"] or 0 for t in trades)

    pnl_curve = []
    acc = 0
    for t in reversed(list(trades)):
        acc += t["profit"] or 0
        pnl_curve.append({"time": t["close_time"], "pnl": round(acc, 2)})

    sym_stats = {}
    for t in trades:
        sym = t["symbol"] or "—"
        if sym not in sym_stats:
            sym_stats[sym] = {"wins": 0, "losses": 0, "pnl": 0}
        sym_stats[sym]["wins" if t["result"] == "win" else "losses"] += 1
        sym_stats[sym]["pnl"] = round(sym_stats[sym]["pnl"] + (t["profit"] or 0), 2)

    return {
        "summary": {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "total_pnl": round(total_profit, 2),
        },
        "pnl_curve": pnl_curve,
        "by_symbol": [{"symbol": k, **v} for k, v in sym_stats.items()],
        "daily_breakdown": [dict(d) for d in daily],
        "trades": [dict(t) for t in trades],
    }
