"""
Motor de trading vía MetaApi — soporta Deriv MT5 y Bridge Markets.
Sin agente Windows local. Misma estrategia: EMA M15 bias + RSI M1 + ATR SL/TP.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable

from mt5_connector import (
    MT5Connector, TF_M1, TF_M15,
    candles_to_arrays, ema, rsi, atr,
)

log = logging.getLogger("mt5_engine")

# ── Configuración estrategia (espeja bot local) ────────────────────────────────
EMA_FAST           = 50
EMA_SLOW           = 200
RSI_PERIOD         = 14
ATR_PERIOD         = 14
ATR_SL_MULTIPLIER  = 1.5
ATR_TP_MULTIPLIER  = 2.5
RISK_PCT           = 3.0         # % balance por trade
MIN_SIGNAL_SCORE   = 65.0        # Bridge: umbral base
MIN_SCORE_OFFHOURS = 78.0        # Forex fuera de sesión Londres/NY
MAX_CONCURRENT     = 2
EARLY_LOSS_USD     = 0.15
TARGET_USD         = 0.35

# Sesión forex Colombia UTC-5
_SESSION_START = 3
_SESSION_END   = 16

FOREX_SYMBOLS = {"EURUSD", "GBPUSD", "XAUUSD"}

# Bridge synthetics — EMA gap de referencia
_EMA_GAP_REF = {
    "EURUSD": 0.05, "GBPUSD": 0.05, "XAUUSD": 0.15,
    "BullX500": 10.0, "BearX500": 10.0,
    "BullX777": 1.2,  "BearX777": 1.2,
    "BullX1000": 1.2, "BearX1000": 0.6,
}

ACTIVE_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "BullX500", "BearX500"]


def _in_session() -> bool:
    now = datetime.now(timezone(timedelta(hours=-5)))
    h = now.hour + now.minute / 60.0
    return _SESSION_START <= h < _SESSION_END


def _calc_lot(balance: float, sl_dist: float, tick_value: float, min_lot: float, step: float, max_lot: float = 5.0) -> float:
    if sl_dist <= 0 or tick_value <= 0:
        return min_lot
    risk_usd = balance * RISK_PCT / 100
    lot = risk_usd / (sl_dist * tick_value)
    lot = max(min_lot, min(max_lot, round(lot // step * step, 8)))
    return lot


def _score(symbol: str, rsi_val: float, ema50: float, ema200: float,
           entry: float, sl: float, tp: float, bias: str) -> float:
    if bias == "bear":
        rsi_score = min(50, max(0, (rsi_val - 50) / 30 * 50))
    else:
        rsi_score = min(50, max(0, (50 - rsi_val) / 30 * 50))

    ref = _EMA_GAP_REF.get(symbol, 0.05)
    gap_pct = abs(ema50 - ema200) / ema200 * 100 if ema200 else 0
    ema_score = min(30, gap_pct / ref * 30)

    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr = tp_dist / sl_dist if sl_dist > 0 else 0
    rr_score = min(20, rr / 2.0 * 20)

    return round(rsi_score + ema_score + rr_score, 1)


class MT5Engine:
    def __init__(
        self,
        account_id: int,
        metaapi_token: str,
        metaapi_account_id: str,
        on_signal: Callable,
        on_trade_closed: Callable,
        on_balance: Callable,
        auto_mode: bool = False,
    ):
        self.account_id          = account_id
        self.metaapi_account_id  = metaapi_account_id
        self.on_signal           = on_signal
        self.on_trade_closed     = on_trade_closed
        self.on_balance          = on_balance
        self.auto_mode           = auto_mode

        self._conn: MT5Connector = MT5Connector(metaapi_token, metaapi_account_id)
        self._running  = False
        self._trading  = False
        self._context_cache: dict = {}
        self._tracked: dict = {}      # position_id -> {signal_id, peak}
        self._last_m15: datetime | None = None

    # ── Control ──────────────────────────────────────────────────────────────

    async def start(self):
        self._running = True
        info = await self._conn.connect()
        log.info(f"[BRIDGE] Engine iniciado | balance={info.get('balance')}")
        asyncio.create_task(self._main_loop())

    async def stop(self):
        self._running = False
        self._trading = False
        await self._conn.disconnect()

    def set_trading(self, active: bool):
        self._trading = active
        log.info(f"[BRIDGE] Trading {'ACTIVO' if active else 'PAUSADO'}")

    def set_auto(self, auto: bool):
        self.auto_mode = auto

    async def execute_signal(self, signal_id: int, signal: dict):
        try:
            sym_info = await self._conn.get_symbol_info(signal["symbol"])
            min_lot  = sym_info.get("minVolume", 0.01)
            step     = sym_info.get("volumeStep", 0.01)
            balance  = await self._conn.get_balance()
            sl_dist  = abs(signal["entry"] - signal["sl"])
            tick_val = sym_info.get("tickValue", 1.0)
            lot = _calc_lot(balance, sl_dist, tick_val, min_lot, step)

            result = await self._conn.place_order(
                symbol    = signal["symbol"],
                direction = signal["direction"],
                lot       = lot,
                sl        = signal["sl"],
                tp        = signal["tp"],
            )
            pos_id = result.get("positionId") or result.get("orderId")
            if pos_id:
                self._tracked[str(pos_id)] = {"signal_id": signal_id, "peak": 0.0}
                log.info(f"[BRIDGE] ✅ Orden ejecutada | {signal['direction'].upper()} {signal['symbol']} lot={lot}")
        except Exception as e:
            log.error(f"[BRIDGE] Error ejecutando orden: {e}")

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _main_loop(self):
        while self._running:
            try:
                balance = await self._conn.get_balance()
                await self.on_balance(balance)
                await self._refresh_m15_if_needed()
                await self._monitor_positions(balance)
                if self._trading:
                    await self._try_signal(balance)
            except Exception as e:
                log.error(f"[BRIDGE] Error ciclo: {e}")
            await asyncio.sleep(60)

    async def _refresh_m15_if_needed(self):
        now = datetime.utcnow()
        if self._last_m15 and (now - self._last_m15).total_seconds() < 900:
            return
        in_sess = _in_session()
        log.info(f"[BRIDGE] {'Sesión activa' if in_sess else '🌙 Fuera de sesión — score ≥78 para forex'}")
        for sym in ACTIVE_SYMBOLS:
            try:
                candles = await self._conn.get_candles(sym, TF_M15, 250)
                if len(candles) < EMA_SLOW:
                    continue
                closes, highs, lows = candles_to_arrays(candles)
                e50  = ema(closes, EMA_FAST)
                e200 = ema(closes, EMA_SLOW)
                bias = "bull" if e50 > e200 else ("bear" if e50 < e200 else "neutral")
                self._context_cache[sym] = {"bias": bias, "ema50": e50, "ema200": e200}
                log.info(f"[STRATEGY] {sym} M15 → bias={bias} | EMA50={e50:.4f} EMA200={e200:.4f}")
            except Exception as e:
                log.warning(f"[STRATEGY] Error M15 {sym}: {e}")
        self._last_m15 = now

    async def _try_signal(self, balance: float):
        positions = await self._conn.get_positions()
        if len(positions) >= MAX_CONCURRENT:
            return

        in_sess = _in_session()
        candidates = []

        for sym in ACTIVE_SYMBOLS:
            ctx = self._context_cache.get(sym)
            if not ctx or ctx["bias"] == "neutral":
                continue
            bias = ctx["bias"]

            try:
                m1 = await self._conn.get_candles(sym, TF_M1, 100)
                if len(m1) < 20:
                    continue
                closes, highs, lows = candles_to_arrays(m1)
                tick  = await self._conn.get_tick(sym)
                bid   = tick.get("bid", closes[-1])
                ask   = tick.get("ask", bid)
                spread = ask - bid

                rsi_val = rsi(closes, RSI_PERIOD)
                atr_val = atr(highs, lows, closes, ATR_PERIOD)
                if atr_val <= 0:
                    continue

                # Spread filter forex (>40% ATR)
                if sym in FOREX_SYMBOLS and spread / atr_val > 0.40:
                    log.info(f"[STRATEGY] ⛔ {sym} spread={spread/atr_val*100:.1f}% ATR — muy caro")
                    continue

                # RSI thresholds
                if sym in FOREX_SYMBOLS:
                    rsi_upper = 42.0 if in_sess else 35.0
                    rsi_lower = 58.0 if in_sess else 65.0
                else:
                    rsi_upper = 58.0
                    rsi_lower = 42.0

                prev_high = float(max(c.get("high", c.get("h", 0)) for c in m1[-4:-1]))
                prev_low  = float(min(c.get("low",  c.get("l", 0)) for c in m1[-4:-1]))
                current   = closes[-1]

                direction = entry = sl = tp = None

                if bias == "bull" and rsi_val > 30 and rsi_val < rsi_upper and current > prev_high:
                    direction = "buy"
                    entry = ask
                    sl    = round(entry - atr_val * ATR_SL_MULTIPLIER, 5)
                    tp    = round(entry + atr_val * ATR_TP_MULTIPLIER, 5)

                elif bias == "bear" and rsi_val < 70 and rsi_val > rsi_lower and current < prev_low:
                    direction = "sell"
                    entry = bid
                    sl    = round(entry + atr_val * ATR_SL_MULTIPLIER, 5)
                    tp    = round(entry - atr_val * ATR_TP_MULTIPLIER, 5)

                if direction is None:
                    log.info(f"[STRATEGY] — {sym} | bias={bias} | RSI={rsi_val:.1f}")
                    continue

                score = _score(sym, rsi_val, ctx["ema50"], ctx["ema200"], entry, sl, tp, bias)
                candidates.append({
                    "symbol": sym, "direction": direction,
                    "entry": round(entry, 5), "sl": sl, "tp": tp,
                    "rsi": round(rsi_val, 2), "atr": round(atr_val, 5),
                    "score": score,
                })

            except Exception as e:
                log.error(f"[STRATEGY] Error señal {sym}: {e}")

        if not candidates:
            return

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]

        is_forex   = best["symbol"] in FOREX_SYMBOLS
        min_score  = MIN_SCORE_OFFHOURS if (is_forex and not in_sess) else MIN_SIGNAL_SCORE
        if best["score"] < min_score:
            log.info(f"[SCHEDULER] ⏭ score={best['score']} < mínimo={min_score}")
            return

        log.info(f"[SCHEDULER] 🏆 {best['direction'].upper()} {best['symbol']} | score={best['score']}")
        best["auto"] = self.auto_mode
        await self.on_signal(best)

        if self.auto_mode:
            await self.execute_signal(-1, best)

    async def _monitor_positions(self, balance: float):
        if not self._tracked:
            return
        try:
            open_positions = await self._conn.get_positions()
            open_ids = {str(p.get("id", p.get("positionId", ""))) for p in open_positions}

            for pos in open_positions:
                pid = str(pos.get("id", pos.get("positionId", "")))
                if pid not in self._tracked:
                    continue
                meta = self._tracked[pid]
                profit = pos.get("profit", 0.0)

                # Actualizar peak
                if profit > meta["peak"]:
                    meta["peak"] = profit

                # Cortar pérdida
                if profit <= -EARLY_LOSS_USD:
                    log.info(f"[MONITOR] ✂️ Límite pérdida ${profit:.2f} | cerrando {pid}")
                    await self._conn.close_position(pid)
                    continue

                # Take profit
                if profit >= TARGET_USD:
                    log.info(f"[MONITOR] 💰 Target ${profit:.2f} alcanzado | cerrando {pid}")
                    await self._conn.close_position(pid)
                    continue

            # Detectar posiciones cerradas por SL/TP de MT5
            closed = [pid for pid in list(self._tracked) if pid not in open_ids]
            for pid in closed:
                meta = self._tracked.pop(pid)
                await self.on_trade_closed({
                    "position_id": pid,
                    "signal_id": meta["signal_id"],
                    "close_time": datetime.utcnow().isoformat(),
                })
                log.info(f"[MONITOR] Posición {pid} cerrada (SL/TP MT5)")

        except Exception as e:
            log.error(f"[MONITOR] Error: {e}")
