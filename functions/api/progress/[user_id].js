function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" }
  });
}

export async function onRequest({ params, request, env }) {
  if (request.method !== "GET") return json({ ok: false, error: "Method not allowed" }, 405);

  const user_id = Number(params.user_id);
  if (!Number.isInteger(user_id) || user_id <= 0) {
    return json({ ok: false, error: "user_id must be a positive integer" }, 400);
  }

  const u = await env.DB.prepare("SELECT id, name FROM users WHERE id = ?").bind(user_id).first();
  if (!u) return json({ ok: false, error: "user not found" }, 404);

  const { results } = await env.DB.prepare(`
    SELECT module_number, completed, completed_at, updated_at
    FROM progress
    WHERE user_id = ?
    ORDER BY module_number ASC
  `)
    .bind(user_id)
    .all();

  const map = {};
  for (let i = 1; i <= 32; i += 1) map[i] = { module_number: i, completed: 0 };
  for (const r of results) map[r.module_number] = r;

  return json({
    ok: true,
    user: u,
    modules: Object.values(map)
  });
}
