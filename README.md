# TradeBot — Bot de señales MT5 (Bridge Markets Demo)

Bot de trading para sintéticos **BullX500 / BearX500** en cuenta DEMO de Bridge Markets.
Opera en modo `confirm`: genera señales y espera tu aprobación en el dashboard antes de ejecutar.

---

## Requisitos previos

- Windows 10/11
- MetaTrader 5 de escritorio instalado y abierto
- Cuenta DEMO de Bridge Markets logueada en el terminal MT5
- Python 3.10 o superior

---

## Instalación paso a paso

### 1. Verificar Python

Abre PowerShell o CMD y ejecuta:
```
python --version
```
Si no está instalado, descárgalo en https://python.org (marcar "Add Python to PATH" durante la instalación).

### 2. Instalar dependencias

Dentro de la carpeta `tradebot/`:
```
pip install -r requirements.txt
```

### 3. Configurar credenciales MT5

Abre `config.py` y completa:
```python
MT5_LOGIN = 123456        # tu número de cuenta demo (entero)
MT5_PASSWORD = "tu_clave"
MT5_SERVER = "BridgeMarkets-Demo"  # nombre exacto del servidor en MT5
```

> **Alternativa:** si el terminal MT5 ya está abierto y logueado manualmente,
> puedes dejar `MT5_LOGIN = 0` y el bot usará la sesión activa sin hacer login.

### 4. Verificar los símbolos en MT5

En el terminal MT5:
- Ve a **Ver → Observación del mercado** (Ctrl+M)
- Busca `BullX500` y `BearX500`
- Si no aparecen, haz clic derecho → **Mostrar todos** y búscalos
- Asegúrate de que tengan precio (tick activo)

### 5. Correr el bot

```
python main.py
```

### 6. Abrir el dashboard

En tu navegador:
```
http://127.0.0.1:8420
```

Desde tu teléfono en la misma red WiFi:
```
http://<IP-de-tu-PC>:8420
```
(Busca tu IP local con `ipconfig` en CMD, busca "Dirección IPv4".)

---

## Horarios de operación

| Hora | Qué hace el bot |
|------|----------------|
| 3:00 pm – 8:00 pm | Solo análisis: lee M15 cada 15 min y registra el sesgo |
| 8:00 pm – 12:00 am | Busca señales en M1 cada minuto, las muestra en el dashboard |
| Fuera de horario | Duerme, no hace nada |

---

## Cómo usar el dashboard

1. Las señales aparecen en la sección **"Señales pendientes"**
2. Cada señal muestra: símbolo, dirección (BUY/SELL), precio de entrada, SL y TP
3. Haz clic en **Confirmar** para que el bot ejecute la orden en MT5
4. Haz clic en **Rechazar** para descartarla
5. El dashboard se actualiza solo cada 10 segundos

---

## Protecciones de riesgo activas

- **Riesgo por operación:** 4% del balance
- **Máximo trades por sesión:** 5
- **Pérdidas consecutivas:** el bot se detiene automáticamente con 2 pérdidas seguidas
- **Límite de pérdida diaria:** si el PnL del día cae a -15%, el bot se apaga solo

---

## Mantener el bot corriendo entre 3pm y 12am

Para evitar que el computador se suspenda durante la sesión:

**Windows 11:**
1. Inicio → Configuración → Sistema → Alimentación y suspensión
2. En **"Suspensión"**, cambia a **"Nunca"** mientras el bot esté activo
3. Vuelve a tu configuración normal después de las 12am

**Alternativa (comando):** abre PowerShell como administrador y ejecuta:
```powershell
powercfg -change -standby-timeout-ac 0
```
Para restaurar después:
```powershell
powercfg -change -standby-timeout-ac 30
```

---

## Reporte de rendimiento

Ve a `/api/report?days=7` o usa los botones del dashboard.

**Checkpoints del plan de prueba:**
- **Día 3–4:** revisar reporte de 3.5 días → decidir ajustes
- **Día 7:** reporte completo → evaluar si continuar o modificar estrategia

---

## Archivos del proyecto

```
tradebot/
  config.py          ← toda la configuración (tocar solo aquí)
  db.py              ← base de datos SQLite (no tocar)
  mt5_connector.py   ← conexión a MT5 (no tocar)
  strategy.py        ← lógica EMA/RSI/ATR
  risk_manager.py    ← gestión de riesgo y límites diarios
  scheduler.py       ← loop de análisis y ejecución
  dashboard.py       ← API FastAPI del dashboard
  main.py            ← punto de entrada
  requirements.txt   ← dependencias Python
  tradebot.db        ← base de datos (se crea sola al correr)
  templates/
    dashboard.html   ← interfaz web
```

---

> ⚠️ **Solo cuenta DEMO.** Este bot es exclusivamente para pruebas en paper trading.
> No se ejecuta en cuentas reales bajo ninguna circunstancia durante esta fase.
