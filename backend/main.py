import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import wp, ty_ly, scenario, admin

app = FastAPI(title="IA Planning Demo", version="1.0.0")

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


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}
