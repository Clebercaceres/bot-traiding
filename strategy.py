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

def analyze_m15_context() -> dict:
    """
    Lee velas M15 del símbolo BULL (el más líquido como referencia),
    calcula EMA50 y EMA200, determina el sesgo, y lo registra en db.
    Retorna: {'bias': 'bull'|'bear'|'neutral', 'symbol': str, 'ema_fast': float, 'ema_slow': float}
    """
    # Usamos BullX500 como índice de referencia para el contexto de mercado
    ref_symbol = config.SYMBOL_BULL
    df = mt5_connector.get_candles(ref_symbol, config.TF_CONTEXT, count=300)

    ema_fast = float(_ema(df["close"], config.EMA_FAST).iloc[-1])
    ema_slow = float(_ema(df["close"], config.EMA_SLOW).iloc[-1])

    if ema_fast > ema_slow:
        bias = "bull"
        active_symbol = config.SYMBOL_BULL
    elif ema_fast < ema_slow:
        bias = "bear"
        active_symbol = config.SYMBOL_BEAR
    else:
        bias = "neutral"
        active_symbol = config.SYMBOL_BULL

    db.log_analysis(ref_symbol, ema_fast, ema_slow, bias)
    print(f"[STRATEGY] M15 contexto → bias={bias} | EMA{config.EMA_FAST}={ema_fast:.4f} EMA{config.EMA_SLOW}={ema_slow:.4f}")

    return {
        "bias": bias,
        "symbol": active_symbol,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
    }


# ─── Entrada M1 ──────────────────────────────────────────────────────────────

def check_entry_signal(context: dict) -> dict | None:
    """
    Evalúa si hay señal de entrada en M1 según el sesgo actual.
    Retorna un dict con la señal si existe, o None.
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
        print(f"[STRATEGY] Señal detectada → {signal['direction'].upper()} {symbol} | RSI={rsi_val:.1f} | entry={signal['entry']} SL={signal['sl']} TP={signal['tp']}")
    else:
        print(f"[STRATEGY] Sin señal | {symbol} | bias={bias} | RSI={rsi_val:.1f} | breakout_high={current_close:.5f}>{prev_high:.5f} breakout_low={current_close:.5f}<{prev_low:.5f}")

    return signal
