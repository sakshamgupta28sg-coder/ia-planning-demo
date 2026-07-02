"""IA Planning desktop launcher.

Starts the FastAPI backend (which serves the bundled Next.js UI at / and the API at
/api) on a local port, then opens it in a native window. Data (DB + seeds) lives in
the per-user OS app-data folder, so every user's plan is private and persists offline.

Runs both from source (python desktop.py) and from a PyInstaller bundle.
"""
import os
import sys
import socket
import threading
import time
import shutil
import urllib.request


def _resource_root():
    """Directory holding backend/, frontend_out/, seeds/ — differs bundle vs source."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass, os.path.join(meipass, "backend"), \
            os.path.join(meipass, "frontend_out"), os.path.join(meipass, "seeds")
    here = os.path.dirname(os.path.abspath(__file__))
    return here, os.path.join(here, "backend"), \
        os.path.join(here, "frontend", "out"), os.path.join(here, "backend", "seeds")


def _app_data_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "IA Planning")
    os.makedirs(d, exist_ok=True)
    return d


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    _root, backend_dir, static_dir, seed_src = _resource_root()
    data_dir = _app_data_dir()

    # First run: seed the user's private data folder from the bundled defaults so
    # their uploads/edits persist there across restarts and app updates.
    user_seeds = os.path.join(data_dir, "seeds")
    if not os.path.isdir(user_seeds) and os.path.isdir(seed_src):
        shutil.copytree(seed_src, user_seeds)

    os.environ["IA_DB_PATH"] = os.path.join(data_dir, "planning.db")   # SQLite (no DATABASE_URL)
    os.environ["IA_SEEDS_DIR"] = user_seeds
    os.environ["IA_STATIC_DIR"] = static_dir

    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)   # so relative module lookups (main:app) and _reload work

    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    def run_server():
        import uvicorn
        uvicorn.run("main:app", host="127.0.0.1", port=port, log_level="warning")

    threading.Thread(target=run_server, daemon=True).start()

    # Wait until the server answers before opening the window.
    for _ in range(150):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)

    try:
        import webview
        webview.create_window("IA Planning", url, width=1440, height=900)
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open(url)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
