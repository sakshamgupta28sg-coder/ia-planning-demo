"""
Admin router — browser-based seed onboarding.

POST /api/admin/upload-seeds accepts the seed CSVs (catalog, supply, budgets
required; sales_history optional), validates the WHOLE set with the same
seed_loader the engine uses, and only writes them to the seeds folder if valid.
Bad uploads are rejected with the exact problem and the live seeds are untouched.

Applying an accepted upload needs a backend restart (the engine builds its data
at startup) — the response says so. GET /api/admin/seed-status reports what is
currently loaded.
"""
import os
import shutil
import sys
import tempfile
import threading

from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import Optional

import seed_loader
from dummy_data import SEEDS_DIR, _SEED

router = APIRouter(prefix="/admin", tags=["admin"])

_REQUIRED = ("catalog", "supply", "budgets")


def _schedule_restart(delay: float = 1.0):
    """Re-exec the server process after `delay`s so saved seeds load via the normal
    (proven, gate-verified) cold-start path. The brief delay lets the HTTP response
    flush first. Env (IA_SEEDS_DIR / IA_DB_PATH) and cwd are inherited across exec,
    so the restarted process reads the same seeds folder — now holding the new data.
    """
    def _restart():
        orig = getattr(sys, "orig_argv", None)
        if orig:
            # Py 3.10+: exact original command (incl. `-m uvicorn`), faithful re-exec.
            os.execv(sys.executable, [sys.executable] + list(orig[1:]))
        else:
            # Older Py: re-launch via `-m uvicorn` with the same uvicorn args. Running
            # uvicorn's __main__.py directly would put its dir on sys.path and shadow
            # stdlib `logging` (circular import), so always go through `-m`.
            os.execv(sys.executable, [sys.executable, "-m", "uvicorn"] + sys.argv[1:])
    threading.Timer(delay, _restart).start()


@router.post("/reload")
def reload_backend():
    """Restart the backend so newly-saved seeds take effect — no manual restart.

    Returns immediately; the server is unavailable for a few seconds, then resumes
    with the new catalog. The frontend polls /seed-status to detect when it's back.
    """
    _schedule_restart()
    return {"status": "reloading", "note": "Backend restarting to load new data."}


@router.get("/seed-status")
def seed_status():
    """What seed the running engine loaded (demo fallback vs CSV), with counts."""
    if _SEED is None:
        return {"source": "demo", "seeds_dir": SEEDS_DIR,
                "sku_count": None, "has_history": False,
                "note": "No catalog.csv present — running built-in demo data."}
    streams_with_history = sorted({(hc, ch) for (hc, ch, _yt, _wn) in _SEED.sales_history})
    return {
        "source": "csv",
        "seeds_dir": SEEDS_DIR,
        "sku_count": len(_SEED.hierarchies) + len(_SEED.new_hierarchies),
        "old_skus": len(_SEED.hierarchies),
        "new_skus": len(_SEED.new_hierarchies),
        "budget_rows": len(_SEED.budgets),
        "has_history": bool(_SEED.sales_history),
        "history_streams": len(streams_with_history),
    }


async def _save(upload: UploadFile, dest: str):
    with open(dest, "wb") as f:
        f.write(await upload.read())


@router.post("/upload-seeds")
async def upload_seeds(
    catalog: UploadFile = File(...),
    supply: UploadFile = File(...),
    budgets: UploadFile = File(...),
    sales_history: Optional[UploadFile] = File(None),
):
    """Validate an uploaded seed set; on success replace the active seeds folder.

    Validation runs against a temp copy via seed_loader — identical rules to engine
    startup — so a set that loads here is guaranteed to load on restart. Nothing is
    written to the live seeds folder unless the whole set validates.
    """
    tmp = tempfile.mkdtemp(prefix="seed_upload_")
    try:
        await _save(catalog, os.path.join(tmp, "catalog.csv"))
        await _save(supply, os.path.join(tmp, "supply.csv"))
        await _save(budgets, os.path.join(tmp, "budgets.csv"))
        has_history = sales_history is not None
        if has_history:
            await _save(sales_history, os.path.join(tmp, "sales_history.csv"))

        # Validate the full set exactly as the engine would at startup.
        try:
            sd = seed_loader.load_seed(tmp)
        except seed_loader.SeedError as e:
            raise HTTPException(status_code=400, detail=f"Seed rejected: {e}")
        if sd is None:
            raise HTTPException(status_code=400, detail="Seed rejected: catalog.csv is empty or unreadable.")

        # Promote: replace catalog/supply/budgets; write or clear sales_history so
        # the live folder always reflects exactly what was uploaded.
        os.makedirs(SEEDS_DIR, exist_ok=True)
        for name in ("catalog.csv", "supply.csv", "budgets.csv"):
            shutil.copy(os.path.join(tmp, name), os.path.join(SEEDS_DIR, name))
        live_history = os.path.join(SEEDS_DIR, "sales_history.csv")
        if has_history:
            shutil.copy(os.path.join(tmp, "sales_history.csv"), live_history)
        elif os.path.isfile(live_history):
            os.remove(live_history)

        return {
            "status": "saved",
            "sku_count": len(sd.hierarchies) + len(sd.new_hierarchies),
            "budget_rows": len(sd.budgets),
            "has_history": has_history,
            "history_rows": len(sd.sales_history),
            "note": "Seeds saved and validated. Restart the backend to load this data.",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
