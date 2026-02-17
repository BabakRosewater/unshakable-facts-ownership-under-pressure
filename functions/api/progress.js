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
  const module_number = Number(body?.module_number);
  const completed = !!body?.completed;

  if (!Number.isInteger(user_id) || user_id <= 0) {
    return json({ ok: false, error: "user_id must be a positive integer" }, 400);
  }
  if (!Number.isInteger(module_number) || module_number < 1 || module_number > 32) {
    return json({ ok: false, error: "module_number must be 1..32" }, 400);
  }

  const u = await env.DB.prepare("SELECT id FROM users WHERE id = ?").bind(user_id).first();
  if (!u) return json({ ok: false, error: "user not found" }, 404);

  const completedInt = completed ? 1 : 0;

  await env.DB.prepare(`
    INSERT INTO progress (user_id, module_number, completed, completed_at, updated_at)
    VALUES (?, ?, ?, CASE WHEN ?=1 THEN datetime('now') ELSE NULL END, datetime('now'))
    ON CONFLICT(user_id, module_number) DO UPDATE SET
      completed=excluded.completed,
      completed_at=CASE WHEN excluded.completed=1 THEN datetime('now') ELSE NULL END,
      updated_at=datetime('now')
  `)
    .bind(user_id, module_number, completedInt, completedInt)
    .run();

  const row = await env.DB.prepare(`
    SELECT user_id, module_number, completed, completed_at, updated_at
    FROM progress WHERE user_id = ? AND module_number = ?
  `)
    .bind(user_id, module_number)
    .first();

  return json({ ok: true, progress: row });
}
