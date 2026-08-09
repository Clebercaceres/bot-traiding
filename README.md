# TradeBot — Bot de señales MT5

Bot de trading algorítmico para índices sintéticos. Soporta **Bridge Markets** (Bear/Bull) y **Deriv** (Volatility). Detecta el broker automáticamente y activa los símbolos correctos.

Modos de ejecución: **Confirmar** (tú decides cada trade) o **Automático** (el bot ejecuta solo).

---

## Requisitos previos

- Windows 10/11
- MetaTrader 5 de escritorio instalado
- Cuenta en Bridge Markets **o** Deriv (demo o real)
- Python 3.10 o superior

---

## Instalación

### 1. Clonar el repositorio

```
git clone <url-del-repo>
cd tradebot/tradebot
```

### 2. Verificar Python

```
python --version
```

Si no está instalado: https://python.org → marcar **"Add Python to PATH"** al instalar.

### 3. Instalar dependencias

```
pip install -r requirements.txt
```

### 4. (Opcional) Configurar auto-login en `config.py`

Si quieres que el bot se conecte solo al arrancar, abre `config.py` y completa:

```python
MT5_LOGIN    = 123456           # número de cuenta (entero)
MT5_PASSWORD = "tu_contraseña"
MT5_SERVER   = "BridgeMarkets-MT5"  # o "Deriv-Demo", "Deriv-Server"
```

> Si lo dejas en cero (`MT5_LOGIN = 0`), el bot arranca sin cuenta y la conectas desde el dashboard.

### 5. Correr el bot

```
python main.py
```

### 6. Abrir el dashboard

```
http://127.0.0.1:8420
```

Desde el celular en la misma red WiFi:
```
http://<IP-de-tu-PC>:8420
```
(Encuentra tu IP con `ipconfig` en CMD → "Dirección IPv4".)

---

## Primer uso — paso a paso en el dashboard

### Paso 1: Conectar tu cuenta MT5

1. Abre el dashboard → tab **Cuenta**
2. Haz clic en **"+ Agregar"**
3. Llena:
   - **Etiqueta:** nombre amigable (ej: "Deriv Demo", "Bridge Real")
   - **Login:** número de cuenta MT5
   - **Contraseña:** clave de la cuenta
   - **Servidor:** usa los botones de sugerencia (Bridge Markets o Deriv) o escríbelo manualmente
4. Haz clic en **"Guardar y conectar"**

El bot detecta automáticamente si es Bridge Markets o Deriv y activa los símbolos correctos:
- **Bridge Markets** → BullX500, BearX500, BullX777, BearX777, BullX1000, BearX1000
- **Deriv** → Volatility 75 Index, Volatility 100 Index

### Paso 2: Activar análisis

Tab **Control** → botón **"▶ Iniciar"** en "Análisis M15".

El bot empieza a leer el mercado cada 15 minutos y calcula el sesgo de tendencia.

### Paso 3: Activar trading

Tab **Control** → botón **"▶ Iniciar"** en "Trading M1".

Ahora el bot busca señales cada minuto.

### Paso 4: Elegir modo de ejecución

En la misma tab Control:

| Modo | Qué hace |
|------|----------|
| 🎮 **Confirmar** | El bot genera la señal, tú haces clic para ejecutarla |
| 🤖 **Automático** | El bot ejecuta la orden directamente sin esperar |

### Paso 5: Ver señales y trades

- **Tab Dashboard** → señales pendientes de confirmación + historial de señales
- **Tab Reporte** → curva de PnL, win rate, historial de trades por cuenta

---

## Gestión de múltiples cuentas

Tab **Cuenta** → lista todas tus cuentas guardadas. Un clic en **"Conectar"** cambia de cuenta: los datos del dashboard (trades, señales, estadísticas del día) son 100% independientes por cuenta.

Para agregar otra cuenta: botón **"+ Agregar"** y repite el proceso.

---

## Protecciones de riesgo

| Parámetro | Valor | Qué hace |
|-----------|-------|----------|
| Riesgo por trade | 2% del balance | Ajusta el lote automáticamente |
| Máx. trades/sesión | 15 | Para después de ese número |
| Pérdidas consecutivas | 4 | Se detiene si pierde 4 seguidas |
| Límite pérdida diaria | 10% | Se apaga si el día pierde >10% |
| Score mínimo señal | 65/100 | Descarta señales de baja calidad |

Todos estos valores se ajustan en `config.py`.

---

## Breakeven y trailing stop

Una vez en trade, el bot gestiona automáticamente:

- **Breakeven** al 50% del SL: mueve el SL a precio de entrada → pérdida = 0
- **Trailing nivel 1** al 120% del SL: arrastra el SL
- **Trailing nivel 2** al 200% del SL: arrastra más cerca
- **Cierre anticipado** al 80% del TP, o al 60% del TP si hay vela de reversión

---

## Estructura del proyecto

```
tradebot/
  config.py          ← TODA la configuración (solo toca este archivo)
  main.py            ← punto de entrada: py main.py
  bot_state.py       ← estado global del bot (análisis, trading, cuenta activa)
  scheduler.py       ← loop principal: M15 cada 15min, M1 cada 1min
  strategy.py        ← lógica EMA50/200 + RSI + breakout 3 velas + ATR
  risk_manager.py    ← cálculo de lotes, límites diarios, pérdidas consecutivas
  mt5_connector.py   ← todo lo que habla con MT5
  db.py              ← SQLite: cuentas, señales, trades, estado diario
  dashboard.py       ← API FastAPI (endpoints del dashboard)
  push_service.py    ← notificaciones push al celular
  requirements.txt   ← dependencias Python
  tradebot.db        ← base de datos LOCAL (no se sube al repo, se crea sola)
  templates/
    dashboard.html   ← interfaz web completa
    sw.js            ← service worker para notificaciones push
```

> `tradebot.db` está en `.gitignore` — cada usuario tiene su propia base de datos con sus trades y cuentas. Al clonar el repo y correr `py main.py` por primera vez, se crea automáticamente limpia.

---

## Evitar que la PC se duerma

El bot necesita que el computador esté activo. En PowerShell (administrador):

```powershell
# Desactivar suspensión mientras operas
powercfg -change -standby-timeout-ac 0

# Restaurar después
powercfg -change -standby-timeout-ac 30
```

O en Windows: Configuración → Sistema → Alimentación y suspensión → **Nunca**.

---

## Brokers soportados

| Broker | Símbolos | Tipo de cuenta |
|--------|----------|----------------|
| Bridge Markets | BullX500, BearX500, BullX777, BearX777, BullX1000, BearX1000 | Demo / Real |
| Deriv | Volatility 75 Index, Volatility 100 Index | Demo / Real |

> El bot detecta el broker automáticamente al conectar y activa los símbolos correctos. No necesitas configurar nada manualmente.

---

## Solución de problemas comunes

**"Terminal: Call failed" al arrancar**
→ Normal los primeros segundos. MT5 tarda en inicializar los feeds. Desaparece solo.

**"Login fallido"**
→ Verifica que el servidor sea exactamente el que muestra MT5 (sensible a mayúsculas).

**Señales no aparecen**
→ Asegúrate de activar primero Análisis, luego Trading. El primer ciclo M15 tarda hasta 15 min.

**Balance no actualiza**
→ Reconecta la cuenta desde tab Cuenta.
