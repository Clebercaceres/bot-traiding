import os
from dotenv import load_dotenv

load_dotenv()

# ── Servidor central ──────────────────────────────────────────────────────────
SERVER_URL  = os.getenv("SERVER_URL", "https://tu-dominio.com")  # sin trailing slash
WS_URL      = SERVER_URL.replace("https://", "wss://").replace("http://", "ws://")

# ── Credenciales de tu cuenta TradeBot ───────────────────────────────────────
TB_EMAIL    = os.getenv("TB_EMAIL", "")
TB_PASSWORD = os.getenv("TB_PASSWORD", "")

# ── Cuenta MT5 a conectar ─────────────────────────────────────────────────────
ACCOUNT_ID  = int(os.getenv("ACCOUNT_ID", "0"))   # id en la DB del servidor
MT5_LOGIN   = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD= os.getenv("MT5_PASSWORD", "")
MT5_SERVER  = os.getenv("MT5_SERVER", "")
MT5_PATH    = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

# ── Estrategia ────────────────────────────────────────────────────────────────
TF_CONTEXT = "M15"
TF_ENTRY   = "M1"
EMA_FAST   = 50
EMA_SLOW   = 200
RSI_PERIOD = 14
RSI_OVERSOLD   = 30
RSI_OVERBOUGHT = 70
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 2.5

# ── Riesgo ────────────────────────────────────────────────────────────────────
RISK_PER_TRADE_PCT    = 2.0
MAX_TRADES_PER_SESSION= 15
MAX_CONCURRENT_TRADES = 1
MIN_SIGNAL_SCORE      = 65.0
MAX_CONSECUTIVE_LOSSES= 4
DAILY_LOSS_LIMIT_PCT  = 10.0
