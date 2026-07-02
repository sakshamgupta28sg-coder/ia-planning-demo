#!/usr/bin/env bash
# Build the IA Planning Mac app locally. Run from the repo root: ./build/build-mac.sh
# Produces: dist/IA Planning.app
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Building the static frontend (UI bundle)"
( cd frontend && NEXT_PUBLIC_API_BASE=/api npm run build )

echo "==> Ensuring the build venv exists"
if [ ! -d .buildvenv ]; then
  uv venv .buildvenv --python 3.12
  VIRTUAL_ENV=.buildvenv uv pip install \
    fastapi==0.111.0 "uvicorn[standard]==0.30.1" python-multipart==0.0.9 \
    pydantic==2.7.1 pywebview pyinstaller
fi

echo "==> Packaging with PyInstaller"
.buildvenv/bin/pyinstaller packaging/ia-planning.spec --noconfirm --distpath dist --workpath build/work

echo "==> Done: dist/IA Planning.app"
echo "   (unsigned — first launch: right-click the app -> Open, then Open again)"
