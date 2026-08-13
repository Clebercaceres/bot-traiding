"""
Gestiona conexiones WebSocket de los agentes MT5.
Cada agente se conecta con su account_id y JWT.
El servidor puede enviarle comandos y recibe eventos del agente.
"""
import asyncio
import json
from fastapi import WebSocket
from datetime import datetime

# account_id -> WebSocket
_connections: dict[int, WebSocket] = {}


async def connect(account_id: int, ws: WebSocket):
    await ws.accept()
    _connections[account_id] = ws
    print(f"[WS] Agente conectado → account_id={account_id}")


def disconnect(account_id: int):
    _connections.pop(account_id, None)
    print(f"[WS] Agente desconectado → account_id={account_id}")


def is_online(account_id: int) -> bool:
    return account_id in _connections


async def send_command(account_id: int, command: str, **kwargs):
    """Envía un comando al agente de esa cuenta."""
    ws = _connections.get(account_id)
    if ws:
        payload = {"type": "command", "command": command, "ts": datetime.utcnow().isoformat(), **kwargs}
        try:
            await ws.send_text(json.dumps(payload))
            return True
        except Exception:
            disconnect(account_id)
    return False


async def broadcast_command(account_ids: list[int], command: str, **kwargs):
    for aid in account_ids:
        await send_command(aid, command, **kwargs)


def online_accounts() -> list[int]:
    return list(_connections.keys())
