"""
Punto de entrada único.
  python main.py
Levanta el scheduler en un hilo y el dashboard (uvicorn) en el hilo principal.
"""
import threading
import signal
import sys

import uvicorn
import config
import db
import mt5_connector
import scheduler
import push_service


def _run_scheduler():
    scheduler.run()


def main():
    print("=" * 50)
    print("  TradeBot — Bridge Markets Demo")
    print("=" * 50)

    # 1. Base de datos
    db.init_db()
    push_service.init_db()
    push_service.init_keys()
    print("[MAIN] Base de datos lista.")

    # 2. Conexión MT5
    try:
        mt5_connector.connect()
    except RuntimeError as e:
        print(f"[MAIN] ❌ Error conectando a MT5: {e}")
        sys.exit(1)

    # 3. Hilo del scheduler
    t = threading.Thread(target=_run_scheduler, daemon=True, name="scheduler")
    t.start()
    print(f"[MAIN] Scheduler iniciado (hilo: {t.name})")
    push_service.notify_bot_started()

    # 4. Manejo limpio de Ctrl+C
    def shutdown(sig, frame):
        print("\n[MAIN] Apagando bot...")
        mt5_connector.disconnect()
        print("[MAIN] MT5 desconectado. Hasta luego.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 5. Dashboard en el hilo principal
    print(f"[MAIN] Dashboard en http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    uvicorn.run(
        "dashboard:app",
        host=config.DASHBOARD_HOST,
        port=config.DASHBOARD_PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
