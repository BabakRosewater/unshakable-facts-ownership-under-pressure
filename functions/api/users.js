function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" }
  });
}

export async function onRequest({ request, env }) {
  if (request.method === "GET") {
    const { results } = await env.DB.prepare(
      "SELECT id, name, created_at FROM users ORDER BY id DESC"
    ).all();
    return json({ ok: true, users: results });
  }

  if (request.method === "POST") {
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Invalid JSON" }, 400);
    }

    const name = (body?.name || "").trim();
    if (!name) return json({ ok: false, error: "name is required" }, 400);

    const res = await env.DB.prepare("INSERT INTO users (name) VALUES (?)")
      .bind(name)
      .run();

    const user = await env.DB.prepare("SELECT id, name, created_at FROM users WHERE id = ?")
      .bind(res.meta.last_row_id)
      .first();

    return json({ ok: true, user }, 201);
  }

  return json({ ok: false, error: "Method not allowed" }, 405);
}
