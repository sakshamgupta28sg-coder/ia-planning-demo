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
  // Optional human-readable label. NOT the key — the machine id enforces the trial,
  // so a different email can't reset anything; email is purely for your dashboard.
  const email = String((req.query && req.query.e) || (req.body && req.body.e) || '')
    .slice(0, 254).trim().toLowerCase() || null;
  try {
    // Vercel Postgres injects POSTGRES_URL; a manual Neon setup uses DATABASE_URL. Accept either.
    const conn = process.env.DATABASE_URL || process.env.POSTGRES_URL || process.env.POSTGRES_PRISMA_URL;
    const sql = neon(conn);
    await sql`CREATE TABLE IF NOT EXISTS trials (
      device text PRIMARY KEY,
      first_seen timestamptz NOT NULL DEFAULT now()
    )`;
    await sql`ALTER TABLE trials ADD COLUMN IF NOT EXISTS email text`;
    // Insert on first sight; on repeat, keep the ORIGINAL first_seen and the FIRST email
    // recorded (a later different email can't overwrite it -> can't be used to game things).
    const rows = await sql`
      INSERT INTO trials (device, email) VALUES (${device}, ${email})
      ON CONFLICT (device) DO UPDATE SET email = COALESCE(trials.email, EXCLUDED.email)
      RETURNING first_seen, email`;
    const firstSeen = new Date(rows[0].first_seen);
    const daysUsed = Math.floor((Date.now() - firstSeen.getTime()) / 86400000);
    const daysLeft = Math.max(0, days - daysUsed);
    const payload = {
      first_seen: firstSeen.toISOString(),
      days_left: daysLeft,
      expired: daysLeft <= 0,
      trial_days: days,
      email: rows[0].email || null,
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
