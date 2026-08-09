"""
Lógica de la estrategia:
  - Contexto M15: EMA50 vs EMA200 → sesgo bull/bear
  - Entrada M1: RSI + rompimiento de vela de confirmación
  - SL/TP basados en ATR
"""
import numpy as np
import pandas as pd
import config
import db
import mt5_connector


# ─── Helpers ────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _atr(df: pd.DataFrame, period: int) -> float:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(com=period - 1, adjust=False).mean().iloc[-1])


# ─── Contexto M15 ────────────────────────────────────────────────────────────

def analyze_m15_context(symbol: str) -> dict:
    """
    Analiza el contexto M15 de UN símbolo específico.
    Retorna: {'bias': 'bull'|'bear'|'neutral', 'symbol': str, 'ema_fast': float, 'ema_slow': float}
    """
    df = mt5_connector.get_candles(symbol, config.TF_CONTEXT, count=300)

    ema_fast = float(_ema(df["close"], config.EMA_FAST).iloc[-1])
    ema_slow = float(_ema(df["close"], config.EMA_SLOW).iloc[-1])

    if ema_fast > ema_slow * 1.0001:
        bias = "bull"
    elif ema_fast < ema_slow * 0.9999:
        bias = "bear"
    else:
        bias = "neutral"

    db.log_analysis(symbol, ema_fast, ema_slow, bias)
    print(f"[STRATEGY] {symbol} M15 → bias={bias} | EMA{config.EMA_FAST}={ema_fast:.4f} EMA{config.EMA_SLOW}={ema_slow:.4f}")

    return {
        "bias": bias,
        "symbol": symbol,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
    }


# ─── Entrada M1 ──────────────────────────────────────────────────────────────

def check_entry_signal(context: dict) -> dict | None:
    """
    Evalúa señal de entrada M1 para el símbolo y sesgo del contexto dado.
    Retorna dict con la señal si hay, o None.
    """
    bias = context["bias"]
    symbol = context["symbol"]

    if bias == "neutral":
        return None

    df = mt5_connector.get_candles(symbol, config.TF_ENTRY, count=100)

    rsi_val = _rsi(df["close"], config.RSI_PERIOD)
    atr_val = _atr(df, config.ATR_PERIOD)

    # Últimas 3 velas completas (excluye la vela actual que aún está formándose)
    last3 = df.iloc[-4:-1]
    prev_high = float(last3["high"].max())
    prev_low = float(last3["low"].min())
    current_close = float(df["close"].iloc[-1])
    current_open = float(df["open"].iloc[-1])

    tick = mt5_connector.get_current_price(symbol)

    signal = None

    if bias == "bull":
        # RSI saliendo de sobreventa + cierre actual rompe máximo de las últimas 3 velas
        rsi_oversold_exit = rsi_val > config.RSI_OVERSOLD and rsi_val < 50
        breakout_bull = current_close > prev_high
        if rsi_oversold_exit and breakout_bull:
            entry = tick.ask
            sl = entry - atr_val * config.ATR_SL_MULTIPLIER
            tp = entry + atr_val * config.ATR_TP_MULTIPLIER
            signal = {
                "symbol": symbol,
                "direction": "buy",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "rsi": round(rsi_val, 2),
                "atr": round(atr_val, 5),
            }

    elif bias == "bear":
        # RSI saliendo de sobrecompra + cierre actual rompe mínimo de las últimas 3 velas
        rsi_overbought_exit = rsi_val < config.RSI_OVERBOUGHT and rsi_val > 50
        breakout_bear = current_close < prev_low
        if rsi_overbought_exit and breakout_bear:
            entry = tick.bid
            sl = entry + atr_val * config.ATR_SL_MULTIPLIER
            tp = entry - atr_val * config.ATR_TP_MULTIPLIER
            signal = {
                "symbol": symbol,
                "direction": "sell",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "rsi": round(rsi_val, 2),
                "atr": round(atr_val, 5),
            }

    if signal:
        signal["score"] = _score_signal(signal, bias, rsi_val, _context_ema_gap(symbol))
        print(f"[STRATEGY] ✅ Señal {signal['direction'].upper()} {symbol} | RSI={rsi_val:.1f} | score={signal['score']:.1f}")
    else:
        print(f"[STRATEGY] — {symbol} | bias={bias} | RSI={rsi_val:.1f}")

    return signal


def _context_ema_gap(symbol: str) -> float:
    """Retorna la separación relativa entre EMA50 y EMA200 del contexto cacheado."""
    try:
        from scheduler import _context_cache
        ctx = _context_cache.get(symbol, {})
        fast = ctx.get("ema_fast", 0)
        slow = ctx.get("ema_slow", 1)
        if slow == 0:
            return 0.0
        return abs(fast - slow) / slow * 100  # % de separación
    except Exception:
        return 0.0


def _score_signal(signal: dict, bias: str, rsi: float, ema_gap_pct: float) -> float:
    """
    Score 0–100 que indica la calidad de la señal.
    Mayor score = mayor convicción = el bot prefiere esta oportunidad.

    Componentes:
    - RSI score (40pts): qué tan extremo está el RSI (más cerca del extremo = mejor)
    - EMA gap score (40pts): qué tan separadas están las EMAs (tendencia más clara = mejor)
    - RR score (20pts): relación riesgo/beneficio de SL vs TP
    """
    # RSI: en bull buscamos RSI saliendo de oversold (30-50), mejor cuanto más cerca de 30
    # En bear buscamos salida de overbought (50-70), mejor cuanto más cerca de 70
    if bias == "bull":
        rsi_score = max(0, (50 - rsi) / 20 * 40)   # RSI=30 → 40pts, RSI=50 → 0pts
    else:
        rsi_score = max(0, (rsi - 50) / 20 * 40)   # RSI=70 → 40pts, RSI=50 → 0pts

    # EMA gap: separación de 0.5% o más → máximo (mercado con tendencia clara)
    ema_score = min(40, ema_gap_pct / 0.5 * 40)

    # RR: TP / SL distancia (RR ≥ 2.5 → 20pts)
    sl_dist = abs(signal["entry"] - signal["sl"])
    tp_dist = abs(signal["tp"] - signal["entry"])
    rr = tp_dist / sl_dist if sl_dist > 0 else 0
    rr_score = min(20, rr / 2.5 * 20)

    return round(rsi_score + ema_score + rr_score, 1)
