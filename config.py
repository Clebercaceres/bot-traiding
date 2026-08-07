"""
Configuración central del bot de trading.
Todo lo que definimos en la conversación está acá. Si quieres cambiar
horarios, riesgo, o el símbolo, este es el único archivo que debes tocar.
"""

# ── Conexión MT5 (cuenta DEMO - Bridge Markets) ──────────────────────────
MT5_LOGIN = 7916999            # tu número de cuenta demo (entero)
MT5_PASSWORD = "R@6cJnMg"        # tu contraseña de la cuenta demo
MT5_SERVER = "BridgeMarkets-MT5"          # nombre exacto del servidor, ej: "BridgeMarkets-Demo"
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# ── Símbolos ──────────────────────────────────────────────────────────────
# El bot elige entre estos dos según el sesgo de tendencia que detecte en M15
SYMBOL_BULL = "BullX500"   # familia: tendencia bajista de fondo, spikes alcistas
SYMBOL_BEAR = "BearX500"   # familia: tendencia alcista de fondo, spikes bajistas

# ── Horarios (hora local de tu computador) ───────────────────────────────
ANALYSIS_START_HOUR = 15   # 3:00 pm - empieza a leer el mercado (M15)
TRADING_START_HOUR = 20    # 8:00 pm - empieza a buscar entradas (M1)
TRADING_END_HOUR = 24      # 12:00 am - cierra la sesión de operación

# ── Timeframes ────────────────────────────────────────────────────────────
TF_CONTEXT = "M15"   # para el sesgo de tendencia (EMA50 vs EMA200)
TF_ENTRY = "M1"       # para el gatillo de entrada (RSI + vela de confirmación)

# ── Estrategia ────────────────────────────────────────────────────────────
EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5   # Stop Loss = ATR * este número
ATR_TP_MULTIPLIER = 2.5   # Take Profit = ATR * este número (RR ≈ 1:1.6)

# ── Gestión de riesgo ─────────────────────────────────────────────────────
RISK_PER_TRADE_PCT = 4.0      # % del capital arriesgado por operación (rango acordado: 3-5%)
MAX_TRADES_PER_SESSION = 5    # tope de operaciones entre 8pm y 12am
MIN_TRADES_TARGET = 3         # el bot prioriza calidad, no está obligado a llegar a 5
MAX_CONSECUTIVE_LOSSES = 2    # 2 pérdidas seguidas -> se detiene la sesión
DAILY_LOSS_LIMIT_PCT = 15.0   # -15% del capital en el día -> el bot se apaga solo

# ── Modo de operación ─────────────────────────────────────────────────────
# "confirm" = el bot solo genera la señal y ESPERA tu clic en el dashboard
# "auto"    = el bot ejecuta directo (NO recomendado todavía, dejar en "confirm")
EXECUTION_MODE = "confirm"

# ── Dashboard local ────────────────────────────────────────────────────────
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8420

# ── Base de datos local (se crea sola, no tocar) ──────────────────────────
DB_PATH = "tradebot.db"
