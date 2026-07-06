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
import json
import hmac
import socket
import shutil
import hashlib
import threading
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

RELOAD_EXIT_CODE = 3

# --- Trial gate (packaged app only; the web server runs main.py and is unaffected) ---
# Per-user N-day trial from first launch. Local + offline, so it's a speed bump, not a
# vault: a determined user on their own machine can still defeat it (the secret ships in
# the bundle, the clock is theirs). It stops casual overuse. Escape hatches for the owner:
# env IA_NO_TRIAL=1, or a ~/.ia_planning_no_trial file. Marker lives OUTSIDE the app-data
# folder so resetting data does not re-arm the trial, and is HMAC-signed so hand-editing
# the dates fails closed (-> expired).
TRIAL_DAYS = 7
_TRIAL_SECRET = b"ia-planning-trial-v1-8f3a2c9e"

# Online trial (airtight against reinstall / new-account gaming): if TRIAL_ENDPOINT is set,
# the app asks the server how many days remain, keyed by a hashed machine fingerprint the
# server can't be tricked into resetting. It keeps working OFFLINE for TRIAL_GRACE_DAYS
# between successful checks; only the first launch strictly needs internet. Empty endpoint
# -> fall back to the offline-only local trial above (nothing to deploy).
TRIAL_ENDPOINT = os.environ.get(
    "IA_TRIAL_ENDPOINT",
    "https://trial-server-sakshamgupta28sg-coders-projects.vercel.app/api/trial")
TRIAL_GRACE_DAYS = 2
_MID_SALT = b"ia-planning-mid-salt-1"


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


def _trial_disabled() -> bool:
    """Owner escape hatches: env var, or a marker file in the home dir."""
    return (os.environ.get("IA_NO_TRIAL") == "1"
            or os.path.exists(os.path.expanduser("~/.ia_planning_no_trial")))


def _trial_marker_path() -> str:
    """Trial state lives beside (not inside) the app-data folder, so resetting the
    app's data does not re-arm the trial."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, ".iaplanning_lic")


def _trial_sig(first: str, seen: str) -> str:
    return hmac.new(_TRIAL_SECRET, f"{first}|{seen}".encode(), hashlib.sha256).hexdigest()


def _machine_id() -> str:
    """A stable, hashed per-machine fingerprint. Survives app reinstall and new user
    accounts (it comes from hardware/OS ids), so the server can't be tricked into a
    fresh trial. Hashed so a raw serial never leaves the machine."""
    raw = ""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True,
                stderr=subprocess.DEVNULL)
            import re
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            raw = m.group(1) if m else ""
        elif sys.platform.startswith("win"):
            out = subprocess.check_output(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                text=True, stderr=subprocess.DEVNULL)
            import re
            m = re.search(r"MachineGuid\s+REG_SZ\s+([\w-]+)", out)
            raw = m.group(1) if m else ""
        else:
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(p):
                    with open(p) as fh:
                        raw = fh.read().strip()
                    break
    except Exception:
        raw = ""
    if not raw:                      # last resort — weaker, but always yields something
        import getpass, platform
        raw = f"{platform.node()}|{getpass.getuser()}"
    return hashlib.sha256(_MID_SALT + raw.encode()).hexdigest()


def _cache_sig(d: dict) -> str:
    msg = f"{d.get('device')}|{d.get('first_seen')}|{d.get('days_left')}|{d.get('checked_at')}"
    return hmac.new(_TRIAL_SECRET, msg.encode(), hashlib.sha256).hexdigest()


def _read_cache(path: str):
    """Return a validated online-cache dict, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if "checked_at" in d and d.get("sig") == _cache_sig(d):
            return d
    except Exception:
        pass
    return None


def _prompt_email() -> str:
    """Ask for an email once (first launch) as a readable dashboard label. Native dialog,
    so it needs no webview session. Returns '' if skipped/unavailable — email is optional
    and never blocks the trial (the machine id is the real key)."""
    msg = "Enter your email to start your IA Planning trial:"
    try:
        if sys.platform == "darwin":
            script = (f'display dialog "{msg}" default answer "" '
                      f'with title "IA Planning" buttons {{"Continue"}} default button "Continue"')
            out = subprocess.check_output(["osascript", "-e", script], text=True,
                                          stderr=subprocess.DEVNULL)
            import re
            m = re.search(r"text returned:(.*)$", out.strip())
            return (m.group(1).strip() if m else "")
        elif sys.platform.startswith("win"):
            import tempfile
            vbs = f'WScript.Echo(InputBox("{msg}","IA Planning"))'
            fh = tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False)
            fh.write(vbs); fh.close()
            out = subprocess.check_output(["cscript", "//Nologo", fh.name], text=True,
                                          stderr=subprocess.DEVNULL)
            os.unlink(fh.name)
            return out.strip()
    except Exception:
        pass
    return ""


def _trial_status_online():
    """Server-authoritative trial with a TRIAL_GRACE_DAYS offline window. Returns
    (ok, days_left, reason)."""
    path = _trial_marker_path()
    now = datetime.now()
    device = _machine_id()
    # First launch on this machine -> collect an email label (optional, one time).
    email = _prompt_email() if not os.path.exists(path) else ""
    # Ask the server.
    try:
        url = f"{TRIAL_ENDPOINT}?d={device}"
        if email:
            url += "&e=" + urllib.parse.quote(email)
        with urllib.request.urlopen(url, timeout=5) as r:
            srv = json.loads(r.read().decode())
        if "days_left" not in srv:
            raise ValueError("bad response")
        cache = {"device": device, "first_seen": srv["first_seen"],
                 "days_left": int(srv["days_left"]), "checked_at": now.isoformat()}
        cache["sig"] = _cache_sig(cache)
        _atomic_write(path, cache)
        if srv.get("expired") or int(srv["days_left"]) <= 0:
            return False, 0, "expired_online"
        return True, int(srv["days_left"]), "ok_online"
    except Exception:
        pass   # offline / server down -> fall through to the grace policy
    # Offline: rely on the last verified check, within the grace window.
    cache = _read_cache(path)
    if not cache or cache.get("device") != device:
        return False, 0, "need_internet_first_run"   # never verified -> fail closed
    try:
        checked = datetime.fromisoformat(cache["checked_at"])
    except Exception:
        return False, 0, "need_internet_first_run"
    if now < checked - timedelta(minutes=5):
        return False, 0, "clock_rollback"
    if now - checked > timedelta(days=TRIAL_GRACE_DAYS):
        return False, 0, "need_internet_grace"
    # Within grace: age the cached days_left by the days elapsed offline.
    days_left = int(cache["days_left"]) - (now - checked).days
    if days_left <= 0:
        return False, 0, "expired_cache"
    return True, days_left, "ok_cache_offline"


def _trial_status():
    """Return (ok, days_left, reason). Online when TRIAL_ENDPOINT is set; otherwise the
    offline-only local trial. Fails closed on tamper/corruption/clock-rollback."""
    if _trial_disabled():
        return True, None, "disabled"
    if TRIAL_ENDPOINT:
        return _trial_status_online()
    path = _trial_marker_path()
    now = datetime.now()
    if not os.path.exists(path):
        f_iso = now.isoformat()
        _write_trial(path, f_iso, f_iso)
        return True, TRIAL_DAYS, "started"
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        f_iso, s_iso, sig = d["f"], d["s"], d["sig"]
        if _trial_sig(f_iso, s_iso) != sig:
            return False, 0, "tampered"
        first = datetime.fromisoformat(f_iso)
        seen = datetime.fromisoformat(s_iso)
    except Exception:
        return False, 0, "invalid"          # corrupt marker -> fail closed
    if now < seen - timedelta(minutes=5):
        return False, 0, "clock_rollback"    # clock set backwards since last launch
    if now - first > timedelta(days=TRIAL_DAYS):
        return False, 0, "expired"
    _write_trial(path, f_iso, now.isoformat())   # refresh last_seen (rollback tripwire)
    return True, max(0, TRIAL_DAYS - (now - first).days), "ok"


def _atomic_write(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _write_trial(path: str, first: str, seen: str):
    _atomic_write(path, {"f": first, "s": seen, "sig": _trial_sig(first, seen)})


def _show_trial_expired(reason: str = ""):
    if reason in ("need_internet_first_run", "need_internet_grace"):
        heading = "Internet connection required"
        body = ("IA Planning needs to connect to the internet to verify your trial. "
                "Please connect and reopen the app.")
    else:
        heading = "Trial period ended"
        body = (f"Your {TRIAL_DAYS}-day trial of IA Planning has expired. Please contact "
                "the sender to continue using the app.")
    html = (
        "<html><body style='font-family:-apple-system,Segoe UI,sans-serif;"
        "background:#0b1220;color:#e2e8f0;display:flex;align-items:center;"
        "justify-content:center;height:100vh;margin:0'><div style='text-align:center;"
        "max-width:440px;padding:24px'><h1 style='font-size:22px;margin:0 0 12px'>"
        f"{heading}</h1><p style='color:#94a3b8;line-height:1.5'>{body}</p></div></body></html>"
    )
    try:
        import webview
        webview.create_window("IA Planning", html=html, width=560, height=380)
        webview.start()
    except Exception:
        print(f"IA Planning: {TRIAL_DAYS}-day trial period has ended.")


def main():
    # Child (server) mode — re-entry of this same binary with the flag set.
    if os.environ.get("IA_SERVER_ONLY") == "1":
        _run_server_only()
        return

    # Trial gate (parent only). Expired -> show a notice and never start the server/UI.
    trial_ok, trial_days_left, _trial_reason = _trial_status()
    if not trial_ok:
        _show_trial_expired(_trial_reason)
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

    ver = ""
    try:
        sys.path.insert(0, backend_dir)
        from _version import __version__ as ver
    except Exception:
        ver = ""
    title = f"IA Planning v{ver}" if ver else "IA Planning"
    if trial_days_left is not None:   # trial active (not the owner escape hatch)
        title += f" · Trial: {trial_days_left} day{'s' if trial_days_left != 1 else ''} left"

    try:
        import webview
        webview.create_window(title, url, width=1440, height=900)
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
