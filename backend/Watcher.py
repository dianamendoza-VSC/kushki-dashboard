import sys
import os
import time

# Asegurar que Python encuentra database.py y etl.py en la misma carpeta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from etl import run_etl
from database import init_db

DATA_INBOX = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data-inbox'
)

class ExcelHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_run = 0
        self.cooldown = 10  # segundos mínimos entre ejecuciones

    def on_modified(self, event):
        self._handle(event)

    def on_created(self, event):
        self._handle(event)

    def _handle(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith('.xlsx'):
            return
        # 🟢 IGNORAR ARCHIVOS TEMPORALES DE EXCEL
        if os.path.basename(event.src_path).startswith('~$'):
            return

        now = time.time()
       
        if now - self.last_run < self.cooldown:
            print(f"⏳ Cooldown activo, ignorando cambio en: {os.path.basename(event.src_path)}")
            return
        self.last_run = now
        print(f"\n📂 Cambio detectado: {os.path.basename(event.src_path)}")
        run_etl()

def start_watcher():
    print(f"👁️  Watcher iniciado — monitoreando: {DATA_INBOX}")
    print(f"   Presiona Ctrl+C para detener\n")

    init_db()

    event_handler = ExcelHandler()
    observer = Observer()
    observer.schedule(event_handler, DATA_INBOX, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Watcher detenido.")
        observer.stop()
    observer.join()

if __name__ == '__main__':
    start_watcher()