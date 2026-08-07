# Prompt para Claude Code — Bot de señales MT5 (Bridge Markets, sintéticos)

Pega este texto completo en Claude Code, parado dentro de esta carpeta (`tradebot/`).

---

Estoy en Windows. Ya tengo instalado el terminal de MetaTrader 5 (MT5) de escritorio,
con mi cuenta DEMO de Bridge Markets logueada y funcionando (ya operaba manualmente ahí).

Ya tengo estos 3 archivos hechos, ábrelos y úsalos como base — no los reescribas desde cero,
solo ajústalos si encuentras algún error real al correrlos:
- `config.py` → toda la configuración (símbolos, horarios, riesgo)
- `db.py` → capa SQLite (analysis_log, signals, trades, daily_state)
- `mt5_connector.py` → conexión a MT5 (login, velas, órdenes, posiciones)

## Lo que necesito que construyas ahora

### 1. `strategy.py`
- Contexto de tendencia en M15: EMA 50 vs EMA 200 (usa `config.EMA_FAST` / `EMA_SLOW`).
  - EMA50 > EMA200 → sesgo "bull" → símbolo a vigilar: `config.SYMBOL_BULL`
  - EMA50 < EMA200 → sesgo "bear" → símbolo a vigilar: `config.SYMBOL_BEAR`
  - Guarda cada lectura con `db.log_analysis(...)`
- Entrada en M1: RSI (`config.RSI_PERIOD`) + confirmación de vela (rompimiento de máximo/mínimo
  de las últimas 3 velas) en la misma dirección del sesgo M15.
  - RSI saliendo de sobreventa (`config.RSI_OVERSOLD`) + sesgo bull + rompimiento alcista → señal buy
  - RSI saliendo de sobrecompra (`config.RSI_OVERBOUGHT`) + sesgo bear + rompimiento bajista → señal sell
- SL/TP basados en ATR (`config.ATR_PERIOD`, `ATR_SL_MULTIPLIER`, `ATR_TP_MULTIPLIER`), no en pips fijos.
- Usa pandas/numpy para los cálculos (EMA, RSI, ATR manual o con librería `ta` si la instalas).

### 2. `risk_manager.py`
- Calcula `lot_size` a partir de `config.RISK_PER_TRADE_PCT`, el balance de la cuenta
  (`mt5_connector.get_account_balance()`), la distancia al SL, y el valor del pip/tick del símbolo
  (usa `mt5_connector.get_symbol_info`).
- Lleva el conteo de pérdidas consecutivas del día (`db.get_today_state` / `update_today_state`).
  Si llega a `config.MAX_CONSECUTIVE_LOSSES` → marca el día como `stopped=1` y no genera más señales.
- Lleva el PnL % acumulado del día. Si cae por debajo de `-config.DAILY_LOSS_LIMIT_PCT` →
  también marca `stopped=1` con `stopped_reason`.
- Expone una función `can_trade_today() -> bool` que el scheduler consulta antes de generar señales.

### 3. `scheduler.py`
- Corre en loop (revisa la hora cada 30-60 segundos).
- Entre `config.ANALYSIS_START_HOUR` y `config.TRADING_START_HOUR`: solo llama a la función de
  contexto M15 de `strategy.py` cada 15 minutos y loguea (no genera señales).
- Entre `config.TRADING_START_HOUR` y `config.TRADING_END_HOUR`:
  - Si `risk_manager.can_trade_today()` es False, no hace nada (sesión detenida).
  - Si ya se alcanzó `config.MAX_TRADES_PER_SESSION` señales hoy, no genera más.
  - Si no, corre la función de entrada M1 de `strategy.py` cada minuto; si hay señal válida,
    calcula lot_size con `risk_manager`, crea la señal con `db.create_signal(...)` (queda en
    estado 'pending' esperando confirmación en el dashboard).
  - Revisa señales en estado 'confirmed' (`db.get_confirmed_signals()`) y las ejecuta con
    `mt5_connector.place_market_order(...)`, actualizando a 'executed' con el ticket.
  - Cada minuto también revisa posiciones abiertas (`mt5_connector.get_open_positions()`); si
    alguna se cerró (ya no aparece), busca el resultado en el historial de MT5
    (`mt5.history_deals_get`) y registra el trade con `db.record_trade_close(...)`, actualizando
    pérdidas consecutivas y PnL del día en `risk_manager`.

### 4. `dashboard.py` (FastAPI, puerto de `config.DASHBOARD_PORT`)
- `GET /` → sirve `templates/dashboard.html`
- `GET /api/pending` → JSON de señales pendientes (`db.get_pending_signals()`)
- `POST /api/signal/{id}/confirm` → marca la señal como 'confirmed'
- `POST /api/signal/{id}/reject` → marca la señal como 'rejected'
- `GET /api/stats` → balance actual, trades de hoy, PnL % de hoy, estado (activo/detenido y por qué)
- `GET /api/report?days=7` → usa `db.performance_report(days_back=days)`

### 5. `templates/dashboard.html`
Dashboard simple de una sola página (HTML + JS vanilla, sin frameworks pesados):
- Arriba: balance, PnL del día, estado (🟢 activo / 🔴 detenido + razón), trades hoy (x/5).
- Sección "Señales pendientes": tarjetas con símbolo, dirección, entry/SL/TP, botones
  Confirmar / Rechazar (llaman a los endpoints POST).
- Sección "Reporte de rendimiento": tabla con el resultado de `/api/report`, con selector para
  ver 3.5 días o 7 días. Incluye win rate, PnL total, y una tabla de trades.
- Que se refresque solo cada 10 segundos (fetch + actualizar el DOM), sin recargar la página.
- Diseño oscuro (dark mode), limpio, legible en una pantalla de laptop y también en el celular
  si abro la IP local desde el teléfono en la misma red.

### 6. `main.py`
- Punto de entrada único. Al correr `python main.py`:
  1. `db.init_db()`
  2. `mt5_connector.connect()`
  3. Levanta el `scheduler.py` en un hilo/thread aparte (loop infinito)
  4. Levanta `dashboard.py` (uvicorn) en el hilo principal
  5. Al cerrar con Ctrl+C, llama `mt5_connector.disconnect()` limpio.

### 7. `requirements.txt`
Incluye: `MetaTrader5`, `pandas`, `numpy`, `fastapi`, `uvicorn`, `jinja2`.

### 8. `README.md`
Instrucciones en español, paso a paso, para correr esto en Windows:
1. Instalar Python 3.10+ si no lo tengo.
2. `pip install -r requirements.txt`
3. Abrir el terminal MT5 de escritorio y loguear la cuenta demo de Bridge Markets.
4. Completar `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` en `config.py` (o dejarlo vacío si ya
   está logueado manualmente en el terminal y no quiero que el script haga login de nuevo).
5. Verificar que `BullX500` y `BearX500` estén visibles en el Market Watch de MT5 (si no,
   agregarlos manualmente ahí primero).
6. Correr `python main.py`.
7. Abrir `http://127.0.0.1:8420` en el navegador para ver el dashboard.
8. Explica cómo dejarlo corriendo entre 3pm y 12am sin que el computador se suspenda
   (desactivar suspensión automática en configuración de energía de Windows durante esas horas).

## Plan de prueba (importante, no lo pierdas de vista)
Esto se va a correr en **cuenta DEMO durante 7 días**. Cada 3.5 días (día 3-4 y día 7) yo voy
a pedir el reporte de `/api/report` para revisar rendimiento y decidir si ajustamos algo de
la estrategia antes de seguir. No se toca cuenta real todavía bajo ninguna circunstancia.

## Nota de riesgo
Bridge Markets es un bróker no regulado según reseñas públicas (WikiFX bajo, quejas de
retiros). Esto es solo para la fase de prueba en demo — no ejecutes ni sugieras ejecutar
nada en cuenta real como parte de esta tarea.

Cuando termines, corre el bot en modo de prueba rápido (aunque sea fuera de horario, forzando
la hora en config para probar) para confirmar que no hay errores antes de dejarlo listo.
