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
    SELECT id, scenario, score, notes, created_at
    FROM scores
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT 200
  `)
    .bind(user_id)
    .all();

  const summary = await env.DB.prepare(`
    SELECT
      COUNT(*) AS count,
      AVG(score) AS avg_score,
      MAX(created_at) AS last_at
    FROM scores
    WHERE user_id = ?
  `)
    .bind(user_id)
    .first();

  return json({
    ok: true,
    user: u,
    summary: {
      count: Number(summary.count || 0),
      avg_score: summary.avg_score ? Number(summary.avg_score).toFixed(2) : null,
      last_at: summary.last_at || null
    },
    scores: results
  });
}
