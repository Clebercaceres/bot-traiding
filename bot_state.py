"""
Estado global compartido entre scheduler y dashboard.
Permite controlar el bot desde la UI sin reiniciar el proceso.
"""
import threading
import config

_lock = threading.Lock()

_state = {
    # Modos activos (control manual desde dashboard)
    "analysis_enabled": False,   # True = estudiando M15
    "trading_enabled": False,    # True = buscando señales M1
    # Ejecución: True = bot ejecuta solo, False = espera confirmación del usuario
    "execution_auto": False,
    # Siempre en modo manual: el usuario decide cuándo analizar y operar
    "manual_mode": True,
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
