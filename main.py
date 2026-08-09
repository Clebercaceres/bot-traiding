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
import bot_state
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

    # 2. Conexión MT5 (opcional al arranque — se puede conectar desde el dashboard)
    try:
        info = mt5_connector.connect()
        # Si hay credenciales en config, detectar broker y activar símbolos
        if info and config.MT5_LOGIN:
            broker = mt5_connector.detect_broker()
            # Buscar o crear la cuenta en DB
            account_id = db.save_account(
                login=info.login,
                password=config.MT5_PASSWORD,
                server=info.server,
                label=f"Cuenta {info.login}",
                broker=broker,
                currency=info.currency,
            )
            db.update_account_balance(account_id, info.balance, info.currency)
            db.activate_symbols_for_broker(broker)
            bot_state.set_active_account(account_id)
    except RuntimeError as e:
        print(f"[MAIN] ⚠️  MT5 no conectado al arranque: {e}")
        print("[MAIN]    → Conéctate desde el dashboard (tab Cuenta) para operar.")

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
