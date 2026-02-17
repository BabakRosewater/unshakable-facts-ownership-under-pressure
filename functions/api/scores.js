function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" }
  });
}

export async function onRequest({ request, env }) {
  if (request.method !== "POST") return json({ ok: false, error: "Method not allowed" }, 405);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "Invalid JSON" }, 400);
  }

  const user_id = Number(body?.user_id);
  const scenario = (body?.scenario || "").trim();
  const score = Number(body?.score);
  const notes = (body?.notes || "").trim();

  if (!Number.isInteger(user_id) || user_id <= 0) {
    return json({ ok: false, error: "user_id must be a positive integer" }, 400);
  }
  if (!scenario) return json({ ok: false, error: "scenario is required" }, 400);
  if (!Number.isFinite(score) || score < 1 || score > 5) {
    return json({ ok: false, error: "score must be 1..5" }, 400);
  }

  const u = await env.DB.prepare("SELECT id FROM users WHERE id = ?").bind(user_id).first();
  if (!u) return json({ ok: false, error: "user not found" }, 404);

  const res = await env.DB.prepare(`
    INSERT INTO scores (user_id, scenario, score, notes)
    VALUES (?, ?, ?, ?)
  `)
    .bind(user_id, scenario, Math.round(score), notes || null)
    .run();

  const row = await env.DB.prepare(`
    SELECT id, user_id, scenario, score, notes, created_at
    FROM scores WHERE id = ?
  `)
    .bind(res.meta.last_row_id)
    .first();

  return json({ ok: true, score: row }, 201);
}
