"""
Estado global compartido entre scheduler y dashboard.
Permite controlar el bot desde la UI sin reiniciar el proceso.
"""
import threading
import config

_lock = threading.Lock()

_state = {
    # Modos activos (override manual)
    "analysis_enabled": False,   # True = estudiando M15
    "trading_enabled": False,    # True = buscando señales M1
    # Horarios configurables (sincronizados con config en arranque)
    "analysis_start": config.ANALYSIS_START_HOUR,
    "trading_start": config.TRADING_START_HOUR,
    "trading_end": config.TRADING_END_HOUR,
    # Control manual override: si True, ignora los horarios automáticos
    "manual_mode": False,
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
    """Vuelve a respetar los horarios configurados."""
    with _lock:
        _state["manual_mode"] = False


def is_analysis_active() -> bool:
    """Devuelve si el análisis debe correr ahora (manual o por horario)."""
    from datetime import datetime
    s = get()
    if s["manual_mode"]:
        return s["analysis_enabled"]
    h = datetime.now().hour + datetime.now().minute / 60
    return s["analysis_start"] <= h < s["trading_end"]


def is_trading_active() -> bool:
    """Devuelve si el trading debe correr ahora (manual o por horario)."""
    from datetime import datetime
    s = get()
    if s["manual_mode"]:
        return s["trading_enabled"]
    h = datetime.now().hour + datetime.now().minute / 60
    end = s["trading_end"] if s["trading_end"] != 24 else 24
    return s["trading_start"] <= h < end
