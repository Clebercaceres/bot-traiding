"""
Base de datos local (SQLite, un solo archivo .db, no necesita servidor).
Guarda todo: cada lectura de tendencia, cada señal generada, y cada trade
cerrado. Con esto se arma el reporte de rendimiento cada 3.5 días.
"""
import sqlite3
from datetime import datetime, date
from contextlib import contextmanager
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT,
    ema_fast REAL,
    ema_slow REAL,
    bias TEXT            -- 'bull' | 'bear' | 'neutral'
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,     -- 'buy' | 'sell'
    entry_price REAL,
    sl REAL,
    tp REAL,
    lot_size REAL,
    rsi_value REAL,
    status TEXT DEFAULT 'pending',  -- pending|confirmed|rejected|executed|closed
    mt5_ticket INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    open_time TEXT,
    close_time TEXT,
    open_price REAL,
    close_price REAL,
    profit REAL,
    result TEXT,          -- 'win' | 'loss'
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS daily_state (
    day TEXT PRIMARY KEY,
    trades_count INTEGER DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,
    pnl_pct REAL DEFAULT 0,
    stopped INTEGER DEFAULT 0,
    stopped_reason TEXT
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


def log_analysis(symbol, ema_fast, ema_slow, bias):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analysis_log (timestamp, symbol, ema_fast, ema_slow, bias) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), symbol, ema_fast, ema_slow, bias),
        )


def create_signal(symbol, direction, entry_price, sl, tp, lot_size, rsi_value):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (timestamp, symbol, direction, entry_price, sl, tp, lot_size, rsi_value, status)
               VALUES (?,?,?,?,?,?,?,?, 'pending')""",
            (datetime.now().isoformat(), symbol, direction, entry_price, sl, tp, lot_size, rsi_value),
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


def record_trade_close(signal_id, open_time, close_time, open_price, close_price, profit):
    result = "win" if profit > 0 else "loss"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO trades (signal_id, open_time, close_time, open_price, close_price, profit, result)
               VALUES (?,?,?,?,?,?,?)""",
            (signal_id, open_time, close_time, open_price, close_price, profit, result),
        )
        conn.execute("UPDATE signals SET status='closed' WHERE id=?", (signal_id,))
    return result


def get_today_state():
    today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM daily_state WHERE day=?", (today,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO daily_state (day) VALUES (?)", (today,))
            row = conn.execute("SELECT * FROM daily_state WHERE day=?", (today,)).fetchone()
        return row


def update_today_state(**fields):
    today = date.today().isoformat()
    get_today_state()  # asegura que exista la fila
    sets = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [today]
    with get_conn() as conn:
        conn.execute(f"UPDATE daily_state SET {sets} WHERE day=?", values)


def performance_report(days_back=7):
    """Resumen para el reporte de checkpoint (cada 3.5 días o al cierre de los 7)."""
    with get_conn() as conn:
        trades = conn.execute(
            f"SELECT * FROM trades WHERE close_time >= datetime('now', '-{days_back} days')"
        ).fetchall()
        daily = conn.execute(
            f"SELECT * FROM daily_state WHERE day >= date('now', '-{days_back} days') ORDER BY day"
        ).fetchall()
    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    total_profit = sum(t["profit"] for t in trades)
    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_profit": round(total_profit, 2),
        "daily_breakdown": [dict(d) for d in daily],
        "trades": [dict(t) for t in trades],
    }
