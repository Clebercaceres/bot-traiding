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
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,          -- nombre exacto en MT5 (ej: BullX500, XAUUSD)
    display_name TEXT NOT NULL,         -- nombre visible en dashboard
    category TEXT DEFAULT 'synthetic',  -- synthetic|cash|forex|crypto|commodity
    active INTEGER DEFAULT 1,
    added_at TEXT DEFAULT (datetime('now'))
);

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
    score REAL,                  -- calidad de la señal 0-100
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
    _seed_symbols()


def _seed_symbols():
    """Inserta los sintéticos más comunes de Deriv/Bridge Markets."""
    defaults = [
        # Bull / Bear
        ("BullX500",   "Bull X500",    "synthetic"),
        ("BearX500",   "Bear X500",    "synthetic"),
        ("BullX777",   "Bull X777",    "synthetic"),
        ("BearX777",   "Bear X777",    "synthetic"),
        ("BullX1000",  "Bull X1000",   "synthetic"),
        ("BearX1000",  "Bear X1000",   "synthetic"),
        # Crash / Boom
        ("Crash300N",  "Crash 300",    "synthetic"),
        ("Crash500",   "Crash 500",    "synthetic"),
        ("Crash1000",  "Crash 1000",   "synthetic"),
        ("Boom300N",   "Boom 300",     "synthetic"),
        ("Boom500",    "Boom 500",     "synthetic"),
        ("Boom1000",   "Boom 1000",    "synthetic"),
        # Volatility
        ("Volatility10Index",  "Volatility 10",  "synthetic"),
        ("Volatility25Index",  "Volatility 25",  "synthetic"),
        ("Volatility50Index",  "Volatility 50",  "synthetic"),
        ("Volatility75Index",  "Volatility 75",  "synthetic"),
        ("Volatility100Index", "Volatility 100", "synthetic"),
    ]
    with get_conn() as conn:
        for name, display, cat in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO symbols (name, display_name, category, active) VALUES (?,?,?,0)",
                (name, display, cat),
            )
        # Solo BullX500 y BearX500 activos por defecto
        conn.execute("UPDATE symbols SET active=1 WHERE name IN ('BullX500','BearX500')")


def activate_symbols_for_broker(broker: str):
    """
    Activa automáticamente los símbolos correctos según el broker detectado.
    broker: 'bridge' | 'deriv' | 'unknown'
    """
    bridge_symbols = ("BullX500", "BearX500", "BullX777", "BearX777", "BullX1000", "BearX1000")
    deriv_symbols  = ("Volatility75Index", "Volatility100Index")

    with get_conn() as conn:
        # Desactivar todos primero
        conn.execute("UPDATE symbols SET active=0")
        if broker == "bridge":
            placeholders = ",".join("?" * len(bridge_symbols))
            conn.execute(f"UPDATE symbols SET active=1 WHERE name IN ({placeholders})", bridge_symbols)
            print(f"[DB] Broker=Bridge → símbolos activados: {', '.join(bridge_symbols)}")
        elif broker == "deriv":
            placeholders = ",".join("?" * len(deriv_symbols))
            conn.execute(f"UPDATE symbols SET active=1 WHERE name IN ({placeholders})", deriv_symbols)
            print(f"[DB] Broker=Deriv → símbolos activados: {', '.join(deriv_symbols)}")
        else:
            # broker desconocido → activar Bear/Bull como fallback
            conn.execute("UPDATE symbols SET active=1 WHERE name IN ('BullX500','BearX500')")
            print("[DB] Broker desconocido → fallback BullX500 + BearX500")


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
            (name.strip(), display_name.strip(), category),
        )


def toggle_symbol(symbol_id, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE symbols SET active=? WHERE id=?", (1 if active else 0, symbol_id))


def delete_symbol(symbol_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM symbols WHERE id=?", (symbol_id,))


def log_analysis(symbol, ema_fast, ema_slow, bias):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analysis_log (timestamp, symbol, ema_fast, ema_slow, bias) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), symbol, ema_fast, ema_slow, bias),
        )


def create_signal(symbol, direction, entry_price, sl, tp, lot_size, rsi_value, score=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (timestamp, symbol, direction, entry_price, sl, tp, lot_size, rsi_value, score, status)
               VALUES (?,?,?,?,?,?,?,?,?, 'pending')""",
            (datetime.now().isoformat(), symbol, direction, entry_price, sl, tp, lot_size, rsi_value, score),
        )
        return cur.lastrowid


def update_signal_status(signal_id, status, mt5_ticket=None):
    with get_conn() as conn:
        if mt5_ticket is not None:
            conn.execute("UPDATE signals SET status=?, mt5_ticket=? WHERE id=?",
                         (status, mt5_ticket, signal_id))
        else:
            conn.execute("UPDATE signals SET status=? WHERE id=?", (status, signal_id))


def get_signals_history(limit: int = 50):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


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


def performance_report(days_back: float = 7, date_from: str = None, date_to: str = None):
    """
    Reporte de rendimiento. Acepta:
    - days_back: últimas N horas/días (float, ej: 2 = 48h)
    - date_from / date_to: rango exacto 'YYYY-MM-DD'
    """
    with get_conn() as conn:
        if date_from and date_to:
            trades = conn.execute(
                "SELECT t.*, s.symbol, s.direction FROM trades t "
                "LEFT JOIN signals s ON t.signal_id = s.id "
                "WHERE date(t.close_time) BETWEEN ? AND ? ORDER BY t.close_time DESC",
                (date_from, date_to)
            ).fetchall()
            daily = conn.execute(
                "SELECT * FROM daily_state WHERE day BETWEEN ? AND ? ORDER BY day",
                (date_from, date_to)
            ).fetchall()
        else:
            hours = int(days_back * 24)
            trades = conn.execute(
                f"SELECT t.*, s.symbol, s.direction FROM trades t "
                f"LEFT JOIN signals s ON t.signal_id = s.id "
                f"WHERE t.close_time >= datetime('now', '-{hours} hours') ORDER BY t.close_time DESC"
            ).fetchall()
            daily = conn.execute(
                f"SELECT * FROM daily_state WHERE day >= date('now', '-{int(days_back)} days') ORDER BY day"
            ).fetchall()

    wins   = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    total_profit = sum(t["profit"] or 0 for t in trades)

    # PnL acumulado por trade (para gráfica de curva)
    pnl_curve = []
    acc = 0
    for t in reversed(list(trades)):
        acc += t["profit"] or 0
        pnl_curve.append({"time": t["close_time"], "pnl": round(acc, 2)})

    # Breakdown por símbolo
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
