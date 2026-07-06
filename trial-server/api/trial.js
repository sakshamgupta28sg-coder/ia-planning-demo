// Trial-check endpoint. Records the first time a machine is seen and reports how many
// days remain. The machine fingerprint (hashed on the client) is the key, so reinstalls,
// new user accounts, and re-downloads on the SAME machine all share one first_seen and
// cannot get a fresh trial. Only a different physical machine starts a new trial.
//
// Deploy: a standalone Vercel project (see README). Env vars required:
//   DATABASE_URL   Neon Postgres connection string (?sslmode=require)
//   TRIAL_SECRET   any long random string (signs the response; keep it secret)
//   TRIAL_DAYS     optional, defaults to 7
import { neon } from '@neondatabase/serverless';
import crypto from 'crypto';

export default async function handler(req, res) {
  const days = parseInt(process.env.TRIAL_DAYS || '7', 10);
  const device = String(
    (req.query && req.query.d) || (req.body && req.body.d) || ''
  ).toLowerCase();
  // client sends sha256 hex (64 chars); accept a small range defensively
  if (!/^[a-f0-9]{16,128}$/.test(device)) {
    return res.status(400).json({ error: 'bad device id' });
  }
  try {
    const sql = neon(process.env.DATABASE_URL);
    await sql`CREATE TABLE IF NOT EXISTS trials (
      device text PRIMARY KEY,
      first_seen timestamptz NOT NULL DEFAULT now()
    )`;
    // Insert on first sight; on repeat, the no-op UPDATE lets us RETURN the original date.
    const rows = await sql`
      INSERT INTO trials (device) VALUES (${device})
      ON CONFLICT (device) DO UPDATE SET device = EXCLUDED.device
      RETURNING first_seen`;
    const firstSeen = new Date(rows[0].first_seen);
    const daysUsed = Math.floor((Date.now() - firstSeen.getTime()) / 86400000);
    const daysLeft = Math.max(0, days - daysUsed);
    const payload = {
      first_seen: firstSeen.toISOString(),
      days_left: daysLeft,
      expired: daysLeft <= 0,
      trial_days: days,
    };
    const sig = crypto
      .createHmac('sha256', process.env.TRIAL_SECRET || '')
      .update(`${payload.first_seen}|${payload.days_left}|${payload.expired}`)
      .digest('hex');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json({ ...payload, sig, server_time: new Date().toISOString() });
  } catch (e) {
    // Fail explicit so the client can apply its offline-grace policy rather than guess.
    return res.status(503).json({ error: 'trial service unavailable' });
  }
}
