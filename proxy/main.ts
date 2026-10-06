// Прокси для Mini App на Deno Deploy: *.vercel.app режется у части российских
// провайдеров (блок по IP), а *.deno.dev открывается. Фронт ходит сюда,
// прокси пересылает запрос в функцию на Vercel и отдаёт ответ как есть —
// CORS и продлённый токен в X-Session-Token приходят от самого API.
const UPSTREAM = "https://interior-narrative-bot.vercel.app";

Deno.serve(async (req) => {
  const url = new URL(req.url);
  // Только API Mini App; вебхук Telegram ходит в Vercel напрямую.
  if (!url.pathname.startsWith("/api/") || url.pathname.startsWith("/api/v1/telegram")) {
    return new Response("Not found", { status: 404 });
  }

  const headers = new Headers(req.headers);
  headers.delete("host");

  const upstream = await fetch(UPSTREAM + url.pathname + url.search, {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "HEAD" ? undefined : req.body,
    redirect: "manual",
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
});
