from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import wp, ty_ly, scenario

app = FastAPI(title="IA Planning Demo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wp.router, prefix="/api")
app.include_router(ty_ly.router, prefix="/api")
app.include_router(scenario.router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}
