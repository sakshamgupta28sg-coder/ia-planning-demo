# Releasing a new version of the IA Planning desktop app

The app is a bundled snapshot of the code. Shipping a new feature = **rebuild + hand out
the new installer**. User data is safe: it lives in the OS app-data folder, separate from
the app bundle, so replacing the app never touches a user's plan.

## Where things live
- **App version:** `backend/_version.py` (`__version__`). Shown in the window title
  ("IA Planning v1.1.0") and at `GET /api/version`.
- **User data (never bundled):** `~/Library/Application Support/IA Planning/` (macOS) /
  `%APPDATA%\IA Planning\` (Windows) — holds `planning.db` + `seeds/`.

## Release checklist
1. **Build & test the feature** on dev as usual (web dev servers, or the byte-identical
   golden checks for engine changes).
2. **Bump the version** in `backend/_version.py` (e.g. `1.0.0` -> `1.1.0`) and commit.
3. **Build the installers** — pick one:
   - **Both OSes (recommended):** `git tag v1.1.0 && git push --tags`
     -> GitHub Actions (Build desktop apps) builds the macOS `.app` and Windows `.exe`
     and uploads both as downloadable artifacts.
   - **Mac only, locally:** `./packaging/build-mac.sh` -> `dist/IA Planning.app`.
4. **Distribute:** send users the new `.app` / `.exe` (email, shared drive, or a GitHub
   Release). They drag it over the old one in Applications.
5. Users reopen the app — **their data is intact**; new DB columns/tables apply
   automatically on startup (`init_db()` runs `CREATE TABLE IF NOT EXISTS` + migrations).

## Notes
- **Unsigned builds:** first launch needs right-click -> Open (macOS) / "More info ->
  Run anyway" (Windows SmartScreen). Signing needs paid certs — optional, for wider
  distribution.
- **Windows CI must be enabled once:** move `packaging/build-apps.yml` to
  `.github/workflows/` and push (needs a token with `workflow` scope).
- **Frequent updates?** Add an auto-updater later (Sparkle on macOS) so the app
  self-updates instead of hand-distributing files.
- **DB schema changes:** additive (new table/column) is automatic. A destructive change
  (rename/drop) needs an explicit migration in `database.py init_db()` — test against a
  copy of a real `planning.db` first.
