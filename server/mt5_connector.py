"""
Wrapper MetaApi para cualquier broker MT5 (Deriv, Bridge Markets, etc.).
MetaApi corre el terminal MT5 en la nube — sin agente Windows local.
Registro: https://app.metaapi.cloud/
"""
import asyncio
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from metaapi_cloud_sdk import MetaApi

log = logging.getLogger("mt5_connector")

# Timeframes MetaApi
TF_M1  = "1m"
TF_M15 = "15m"


class MT5Connector:
    def __init__(self, metaapi_token: str, metaapi_account_id: str):
        self._token      = metaapi_token
        self._account_id = metaapi_account_id
        self._api: MetaApi | None = None
        self._conn = None   # RpcConnection
        self._account = None

    async def connect(self) -> dict:
        self._api     = MetaApi(self._token)
        self._account = await self._api.metatrader_account_api.get_account(self._account_id)

        if self._account.state not in ("DEPLOYED", "DEPLOYING"):
            await self._account.deploy()
        await self._account.wait_connected()

        self._conn = self._account.get_rpc_connection()
        await self._conn.connect()
        await self._conn.wait_synchronized()

        info = await self._conn.get_account_information()
        log.info(f"[BRIDGE] Conectado → balance={info.get('balance')} {info.get('currency')}")
        return info

    async def disconnect(self):
        if self._conn:
            await self._conn.close()
        if self._api:
            self._api.close()

    async def get_account_info(self) -> dict:
        return await self._conn.get_account_information()

    async def get_balance(self) -> float:
        info = await self._conn.get_account_information()
        return info.get("balance", 0.0)

    async def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> list[dict]:
        start = datetime.now(timezone.utc) - timedelta(hours=count // 4 + 2)
        bars = await self._conn.get_historical_candles(symbol, timeframe, start, count)
        return bars or []

    async def get_tick(self, symbol: str) -> dict:
        return await self._conn.get_symbol_price(symbol)

    async def get_symbol_info(self, symbol: str) -> dict:
        return await self._conn.get_symbol_specification(symbol)

    async def place_order(
        self,
        symbol: str,
        direction: str,  # "buy" | "sell"
        lot: float,
        sl: float,
        tp: float,
        comment: str = "tradebot",
    ) -> dict:
        opts = {"comment": comment, "clientId": "tradebot"}
        if direction == "buy":
            result = await self._conn.create_market_buy_order(symbol, lot, sl, tp, opts)
        else:
            result = await self._conn.create_market_sell_order(symbol, lot, sl, tp, opts)
        return result

    async def close_position(self, position_id: str) -> dict:
        return await self._conn.close_position(position_id)

    async def modify_position(self, position_id: str, sl: float | None = None, tp: float | None = None):
        await self._conn.modify_position(position_id, stop_loss=sl, take_profit=tp)

    async def get_positions(self) -> list[dict]:
        positions = await self._conn.get_positions()
        return positions or []


# ── Provisionar cuenta nueva en MetaApi ───────────────────────────────────────

async def provision_account(
    metaapi_token: str,
    login: int,
    password: str,
    server: str,
    label: str = "TradeBot",
) -> str:
    """
    Registra la cuenta MT5 en MetaApi y devuelve el metaapi_account_id.
    Llamar una sola vez al crear la cuenta. Guardar el ID resultante en DB.
    """
    api = MetaApi(metaapi_token)
    accounts = await api.metatrader_account_api.get_accounts_with_infinite_scroll_pagination()
    # Reusar si ya existe
    for acc in accounts:
        if str(acc.login) == str(login) and acc.server == server:
            api.close()
            return acc.id

    account = await api.metatrader_account_api.create_account({
        "name":     label,
        "type":     "cloud",
        "login":    str(login),
        "password": password,
        "server":   server,
        "platform": "mt5",
        "magic":    990011,
    })
    api.close()
    return account.id


# ── Helpers de análisis técnico ────────────────────────────────────────────────

def candles_to_arrays(candles: list[dict]):
    closes = np.array([float(c.get("close", c.get("c", 0))) for c in candles])
    highs  = np.array([float(c.get("high",  c.get("h", 0))) for c in candles])
    lows   = np.array([float(c.get("low",   c.get("l", 0))) for c in candles])
    return closes, highs, lows


def ema(arr: np.ndarray, period: int) -> float:
    if len(arr) < period:
        return float(arr[-1])
    k = 2 / (period + 1)
    val = float(arr[0])
    for v in arr[1:]:
        val = v * k + val * (1 - k)
    return val


def rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g  = np.mean(gains[-period:])
    avg_l  = np.mean(losses[-period:])
    if avg_l == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_l)


def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < 2:
        return float(highs[-1] - lows[-1])
    tr = np.maximum(highs[1:] - lows[1:],
         np.maximum(np.abs(highs[1:] - closes[:-1]),
                    np.abs(lows[1:]  - closes[:-1])))
    return float(np.mean(tr[-period:]))
