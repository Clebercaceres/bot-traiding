from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    email         = Column(String, unique=True, nullable=False, index=True)
    name          = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"

    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    label          = Column(String, nullable=False)
    login          = Column(Integer, nullable=False)
    password            = Column(String, nullable=True)  # encriptado con Fernet
    api_token           = Column(String, nullable=True)  # Deriv API token
    metaapi_account_id  = Column(String, nullable=True)  # ID en MetaApi (Deriv + Bridge cloud)
    server              = Column(String, nullable=False)
    broker         = Column(String, default="unknown")
    currency       = Column(String, default="USD")
    balance        = Column(Float, default=0.0)
    is_active      = Column(Boolean, default=True)    # cuenta activa/seleccionada
    agent_online   = Column(Boolean, default=False)   # agente conectado por WS
    last_connected = Column(DateTime)
    created_at     = Column(DateTime, default=datetime.utcnow)

    user    = relationship("User", back_populates="accounts")
    signals = relationship("Signal", back_populates="account", cascade="all, delete-orphan")
    trades  = relationship("Trade", back_populates="account", cascade="all, delete-orphan")


class Signal(Base):
    __tablename__ = "signals"

    id          = Column(Integer, primary_key=True)
    account_id  = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    timestamp   = Column(DateTime, default=datetime.utcnow)
    symbol      = Column(String, nullable=False)
    direction   = Column(String, nullable=False)   # buy | sell
    entry_price = Column(Float)
    sl          = Column(Float)
    tp          = Column(Float)
    lot_size    = Column(Float)
    rsi_value   = Column(Float)
    score       = Column(Float)
    status      = Column(String, default="pending")  # pending|confirmed|rejected|executed|closed
    mt5_ticket  = Column(Integer)

    account = relationship("Account", back_populates="signals")
    trade   = relationship("Trade", back_populates="signal", uselist=False)


class Trade(Base):
    __tablename__ = "trades"

    id          = Column(Integer, primary_key=True)
    account_id  = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    signal_id   = Column(Integer, ForeignKey("signals.id"))
    open_time   = Column(DateTime)
    close_time  = Column(DateTime)
    open_price  = Column(Float)
    close_price = Column(Float)
    profit      = Column(Float)
    result      = Column(String)   # win | loss

    account = relationship("Account", back_populates="trades")
    signal  = relationship("Signal", back_populates="trade")


class DailyState(Base):
    __tablename__ = "daily_state"

    id                = Column(Integer, primary_key=True)
    account_id        = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    day               = Column(String, nullable=False)   # YYYY-MM-DD
    trades_count      = Column(Integer, default=0)
    consecutive_losses = Column(Integer, default=0)
    pnl_pct           = Column(Float, default=0.0)
    stopped           = Column(Boolean, default=False)
    stopped_reason    = Column(Text)
