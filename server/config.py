import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-32chars!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 días

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tradebot.db").replace(
    "postgres://", "postgresql://", 1
)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")

# MetaApi — para conectar cuentas Bridge/MT5 sin agente local
# Obtén tu token en: https://app.metaapi.cloud/token
METAAPI_TOKEN = os.getenv("METAAPI_TOKEN", "")
