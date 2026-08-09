"""
Estado global compartido entre scheduler y dashboard.
Permite controlar el bot desde la UI sin reiniciar el proceso.
"""
import threading
import config

_lock = threading.Lock()

_state = {
    "analysis_enabled": False,
    "trading_enabled": False,
    "execution_auto": False,
    "manual_mode": True,
    "active_account_id": None,  # id de la cuenta activa en DB
}


def get() -> dict:
    with _lock:
        return dict(_state)


def set_analysis(enabled: bool):
    with _lock:
        _state["analysis_enabled"] = enabled
        _state["manual_mode"] = True


def set_trading(enabled: bool):
    with _lock:
        _state["trading_enabled"] = enabled
        if enabled:
            _state["analysis_enabled"] = True  # trading implica análisis activo
        _state["manual_mode"] = True


def set_execution_auto(auto: bool):
    """True = bot ejecuta señales automáticamente. False = espera confirmación."""
    with _lock:
        _state["execution_auto"] = auto


def set_hours(analysis_start: int, trading_start: int, trading_end: int):
    with _lock:
        _state["analysis_start"] = analysis_start
        _state["trading_start"] = trading_start
        _state["trading_end"] = trading_end
        _state["manual_mode"] = False  # vuelve a modo horario automático
        # Actualizar config en memoria
        config.ANALYSIS_START_HOUR = analysis_start
        config.TRADING_START_HOUR = trading_start
        config.TRADING_END_HOUR = trading_end


def stop_all():
    with _lock:
        _state["analysis_enabled"] = False
        _state["trading_enabled"] = False
        _state["manual_mode"] = True


def auto_mode():
    """Mantiene manual_mode=True; el usuario controla análisis y trading desde el dashboard."""
    with _lock:
        _state["manual_mode"] = True


def is_analysis_active() -> bool:
    return get()["analysis_enabled"]


def is_trading_active() -> bool:
    return get()["trading_enabled"]


def set_active_account(account_id: int):
    with _lock:
        _state["active_account_id"] = account_id


def get_active_account_id() -> int | None:
    with _lock:
        return _state.get("active_account_id")
