# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the IA Planning desktop app (Mac .app / Windows .exe).
# Build from the repo root:  pyinstaller build/ia-planning.spec
# Requires: frontend/out/ already built (next build) and the build venv deps installed.
import os

ROOT = os.getcwd()  # pyinstaller is invoked from the repo root

datas = [
    (os.path.join(ROOT, "frontend", "out"), "frontend_out"),  # bundled UI
    (os.path.join(ROOT, "backend"), "backend"),               # app code (imported at runtime)
    (os.path.join(ROOT, "backend", "seeds"), "seeds"),        # default seed set
]

# The backend is imported dynamically via uvicorn.run("main:app"), so name its modules
# and uvicorn's dynamically-loaded protocol/loop submodules explicitly.
hiddenimports = [
    "main", "dummy_data", "database", "seed_loader", "_version",
    "routers.wp", "routers.ty_ly", "routers.scenario", "routers.admin",
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
]

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[os.path.join(ROOT, "backend")],   # so Analysis can import the app modules
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["psycopg2", "psycopg2.extras"],  # local app is SQLite-only
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="IA Planning",
    console=False,          # windowed app, no terminal
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="IA Planning")

# macOS: wrap into a proper .app bundle
app = BUNDLE(
    coll,
    name="IA Planning.app",
    bundle_identifier="com.iaplanning.app",
)
