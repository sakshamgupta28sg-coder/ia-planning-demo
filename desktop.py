"""IA Planning desktop launcher.

Architecture (so "apply new seeds" reload works without killing the window):
- Parent process: opens the native window at a FIXED local port and supervises a
  child server process, restarting it when it exits with RELOAD_EXIT_CODE.
- Child process (same binary, IA_SERVER_ONLY=1): runs FastAPI (UI at /, API at /api)
  on that port. The /api/admin/reload endpoint calls os._exit(RELOAD_EXIT_CODE) in
  desktop mode, so the parent restarts it -> new seeds load, same port, window resumes.

Data (DB + seeds) lives in the per-user OS app-data folder: private, persists offline.
Runs both from source (python desktop.py) and from a PyInstaller bundle.
"""
import os
import sys
import time
import socket
import shutil
import threading
import subprocess
import urllib.request

RELOAD_EXIT_CODE = 3


def _resource_root():
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return (os.path.join(meipass, "backend"),
                os.path.join(meipass, "frontend_out"),
                os.path.join(meipass, "seeds"))
    here = os.path.dirname(os.path.abspath(__file__))
    return (os.path.join(here, "backend"),
            os.path.join(here, "frontend", "out"),
            os.path.join(here, "backend", "seeds"))


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


def _pick_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_server_only():
    """Child mode: serve the app on the agreed port. Retry the bind briefly so a
    reload (previous server just exited) doesn't race the port release."""
    port = int(os.environ["IA_DESKTOP_PORT"])
    sys.path.insert(0, os.environ["IA_BACKEND_DIR"])
    os.chdir(os.environ["IA_BACKEND_DIR"])
    import uvicorn
    for attempt in range(20):
        try:
            uvicorn.run("main:app", host="127.0.0.1", port=port, log_level="warning")
            return
        except OSError:
            time.sleep(0.25)   # port still in TIME_WAIT from the old server; retry
    raise SystemExit("could not bind server port")


def main():
    # Child (server) mode — re-entry of this same binary with the flag set.
    if os.environ.get("IA_SERVER_ONLY") == "1":
        _run_server_only()
        return

    backend_dir, static_dir, seed_src = _resource_root()
    data_dir = _app_data_dir()

    # First run: copy bundled seeds into the user's private folder so their uploads/edits
    # persist there across restarts and app updates.
    user_seeds = os.path.join(data_dir, "seeds")
    if not os.path.isdir(user_seeds) and os.path.isdir(seed_src):
        shutil.copytree(seed_src, user_seeds)

    port = _pick_port()
    url = f"http://127.0.0.1:{port}/"

    child_env = dict(os.environ)
    child_env.update({
        "IA_SERVER_ONLY": "1",
        "IA_DESKTOP": "1",                  # tells /api/admin/reload to os._exit for restart
        "IA_DESKTOP_PORT": str(port),
        "IA_BACKEND_DIR": backend_dir,
        "IA_DB_PATH": os.path.join(data_dir, "planning.db"),   # SQLite, persistent
        "IA_SEEDS_DIR": user_seeds,
        "IA_STATIC_DIR": static_dir,
    })

    stop = threading.Event()
    current = {"proc": None}

    def supervise():
        while not stop.is_set():
            proc = subprocess.Popen([sys.executable], env=child_env)
            current["proc"] = proc
            proc.wait()
            # Reload requested -> loop restarts the server (new seeds, same port).
            if proc.returncode != RELOAD_EXIT_CODE or stop.is_set():
                break

    threading.Thread(target=supervise, daemon=True).start()

    # Wait until the server answers before opening the window.
    for _ in range(200):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)

    try:
        import webview
        webview.create_window("IA Planning", url, width=1440, height=900)
        webview.start()   # blocks until the window is closed
    except Exception:
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    finally:
        stop.set()
        proc = current.get("proc")
        if proc and proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    main()
