# IA Planning — trial server

A tiny serverless endpoint (`/api/trial`) that enforces a **per-machine free trial** for the
desktop app. It records the first time a machine is seen and returns the days remaining, so
reinstalling the app, making a new user account, or re-downloading on the **same machine**
can't get a fresh trial. Only a different physical machine starts a new trial.

Free to run: one Vercel function + your existing Neon Postgres. Well inside both free tiers.

## Deploy (one time, ~5 min)

1. Install the CLI and log in (browser opens):
   ```bash
   npm i -g vercel
   vercel login
   ```
2. From this folder, deploy:
   ```bash
   cd trial-server
   vercel --prod
   ```
   Accept the defaults (new project, e.g. `ia-planning-trial`).
3. In the Vercel dashboard for this project → **Settings → Environment Variables**, add:
   | Name | Value |
   |------|-------|
   | `DATABASE_URL` | your Neon connection string (`postgresql://…?sslmode=require`) |
   | `TRIAL_SECRET` | any long random string (e.g. `openssl rand -hex 32`) |
   | `TRIAL_DAYS`   | `7` (optional) |
   Then **redeploy** (`vercel --prod` again) so the vars take effect.
4. Note the URL Vercel prints, e.g. `https://ia-planning-trial.vercel.app`. The endpoint is
   `https://ia-planning-trial.vercel.app/api/trial`.

## Test it
```bash
curl "https://<your-project>.vercel.app/api/trial?d=$(python3 -c 'print("a"*64)')"
# -> {"first_seen":"...","days_left":7,"expired":false,"trial_days":7,"sig":"...","server_time":"..."}
# call it again -> same first_seen (the trial doesn't reset)
```

## Then
Give the endpoint URL back to Claude (or set it yourself): it goes into `desktop.py`
`TRIAL_ENDPOINT`, and the app is rebuilt so the installers check this server. No secrets are
baked into the app — only the public URL.

## Notes
- The client sends a **hashed** machine id, never a raw hardware serial (privacy).
- The app keeps working **offline** for a 2-day grace window between successful checks; only
  the first launch strictly needs internet.
- Reset a specific machine's trial (e.g. for a real buyer): delete its row —
  `DELETE FROM trials WHERE device = '<hash>';` — or drop everyone with `TRUNCATE trials;`.
