"""
Servicio de notificaciones Web Push (VAPID).
Genera las claves automáticamente en el primer arranque y las guarda en vapid_keys.json.
"""
import json
import os
import sqlite3
import threading
from pathlib import Path

_KEYS_FILE = Path(__file__).parent / "vapid_keys.json"
_DB_PATH = "tradebot.db"
_lock = threading.Lock()

# Claves VAPID (se cargan/generan al importar)
PUBLIC_KEY: str = ""
PRIVATE_KEY: str = ""


def _generate_and_save_keys():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    import base64

    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    # Serializar en formato raw base64url (sin encabezados PEM)
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption
    )
    pub_bytes = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    priv_numbers = private_key.private_numbers()
    priv_bytes = priv_numbers.private_value.to_bytes(32, "big")

    pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode()

    keys = {"public": pub_b64, "private": priv_b64}
    _KEYS_FILE.write_text(json.dumps(keys, indent=2))
    return pub_b64, priv_b64


def init_keys():
    global PUBLIC_KEY, PRIVATE_KEY
    if _KEYS_FILE.exists():
        data = json.loads(_KEYS_FILE.read_text())
        PUBLIC_KEY = data["public"]
        PRIVATE_KEY = data["private"]
        print(f"[PUSH] Claves VAPID cargadas.")
    else:
        PUBLIC_KEY, PRIVATE_KEY = _generate_and_save_keys()
        print(f"[PUSH] Claves VAPID generadas y guardadas.")


def init_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_subscription(endpoint: str, p256dh: str, auth: str):
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO push_subscriptions (endpoint, p256dh, auth) VALUES (?,?,?)",
        (endpoint, p256dh, auth)
    )
    conn.commit()
    conn.close()


def delete_subscription(endpoint: str):
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
    conn.commit()
    conn.close()


def get_subscriptions():
    conn = sqlite3.connect(_DB_PATH)
    rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()
    conn.close()
    return rows


def send_notification(title: str, body: str, icon: str = "📊", tag: str = "tradebot"):
    """Envía push a todas las suscripciones registradas."""
    subs = get_subscriptions()
    if not subs:
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[PUSH] pywebpush no instalado, notificación omitida.")
        return

    payload = json.dumps({"title": title, "body": body, "tag": tag})

    dead = []
    for endpoint, p256dh, auth in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=payload,
                vapid_private_key=PRIVATE_KEY,
                vapid_claims={"sub": "mailto:tradebot@local.dev"},
            )
        except WebPushException as e:
            code = e.response.status_code if e.response else 0
            if code in (404, 410):  # suscripción expirada
                dead.append(endpoint)
            else:
                print(f"[PUSH] Error enviando notificación: {e}")
        except Exception as e:
            print(f"[PUSH] Error inesperado: {e}")

    for ep in dead:
        delete_subscription(ep)


# ── Atajos por evento ─────────────────────────────────────────────────────────

def notify_signal(symbol: str, direction: str, entry: float, sl: float, tp: float):
    icon = "🟢" if direction == "buy" else "🔴"
    send_notification(
        title=f"{icon} Nueva señal — {direction.upper()} {symbol}",
        body=f"Entrada: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f}\n¡Confirma en el dashboard!",
        tag="signal",
    )

def notify_trade_executed(symbol: str, direction: str, ticket: int, price: float):
    icon = "🟢" if direction == "buy" else "🔴"
    send_notification(
        title=f"{icon} Orden abierta — {direction.upper()} {symbol}",
        body=f"Ticket #{ticket} | Precio: {price:.5f}",
        tag=f"exec-{ticket}",
    )

def notify_trade_closed(symbol: str, profit: float, result: str):
    icon = "✅" if result == "win" else "❌"
    sign = "+" if profit >= 0 else ""
    send_notification(
        title=f"{icon} Trade cerrado — {symbol}",
        body=f"Resultado: {result.upper()} | P&L: {sign}{profit:.2f}",
        tag="closed",
    )

def notify_session_stopped(reason: str):
    send_notification(
        title="⛔ Sesión detenida",
        body=reason,
        tag="stopped",
    )

def notify_bot_started():
    send_notification(
        title="🤖 TradeBot iniciado",
        body="El bot está activo y monitoreando el mercado.",
        tag="started",
    )

def notify_analysis(bias: str, symbol: str):
    icon = "📈" if bias == "bull" else "📉" if bias == "bear" else "➡️"
    send_notification(
        title=f"{icon} Sesgo M15 actualizado",
        body=f"Bias: {bias.upper()} | Símbolo activo: {symbol}",
        tag="analysis",
    )
