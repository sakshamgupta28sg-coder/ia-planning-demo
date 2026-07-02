import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import wp, ty_ly, scenario, admin
try:
    from _version import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"

app = FastAPI(title="IA Planning Demo", version=APP_VERSION)


@app.get("/api/version")
def version():
    return {"version": APP_VERSION}

# Local dev origins always allowed; add deployed frontends (e.g. the Vercel URL)
# via ALLOWED_ORIGINS="https://foo.vercel.app,https://bar" — no code change to deploy.
_origins = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3012"]
_origins += [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wp.router, prefix="/api")
app.include_router(ty_ly.router, prefix="/api")
app.include_router(scenario.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

# Desktop-app mode: the launcher sets IA_STATIC_DIR to the bundled static frontend
# (Next.js export), so FastAPI serves the whole UI at "/" on the same origin as /api.
# Unset (web/dev, where Next serves the UI separately) -> keep the JSON health root.
# Mounted AFTER the /api routers so API paths always win.
_STATIC_DIR = os.environ.get("IA_STATIC_DIR")
if _STATIC_DIR and os.path.isdir(_STATIC_DIR):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="ui")
else:
    @app.get("/")
    def root():
        return {"status": "ok", "docs": "/docs"}
