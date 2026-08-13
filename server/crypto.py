"""
Encriptación simétrica Fernet para contraseñas MT5.
FIELD_ENCRYPTION_KEY en .env — genera con:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from cryptography.fernet import Fernet, InvalidToken

_raw = os.getenv("FIELD_ENCRYPTION_KEY", "")
_fernet: Fernet | None = None

if _raw:
    try:
        _fernet = Fernet(_raw.encode())
    except Exception:
        pass


def encrypt(value: str) -> str:
    if not _fernet:
        return value  # sin clave → guarda en claro (dev local)
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not _fernet:
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return value  # ya era texto plano (migración gradual)
