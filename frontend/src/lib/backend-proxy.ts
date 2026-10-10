/** Resolve at request time so one standalone image works in any deployment. */
export function getBackendUrl(): string {
  return (process.env.BACKEND_URL || process.env.API_URL || (
    process.env.NODE_ENV === "development"
      ? "http://127.0.0.1:8000"
      : "http://backend:8000"
  )).replace(/\/+$/, "");
}

function endToEndHeaders(source: Headers): Headers {
  const headers = new Headers(source);
  // Connection may nominate additional hop-by-hop fields.
  for (const name of (headers.get("connection") || "").split(",")) {
    if (name.trim()) headers.delete(name.trim());
  }
  for (const name of [
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "host",
  ]) headers.delete(name);
  return headers;
}

/** Stream requests and responses, including SSE and ranged media, without buffering. */
export async function proxyBackendRequest(request: Request): Promise<Response> {
  const incoming = new URL(request.url);
  const path = incoming.pathname.replace(/^\/api(?=\/|$)/, "") || "/";
  const headers = endToEndHeaders(request.headers);
  headers.delete("content-length");
  // Fetch decompresses upstream responses. Prefer identity and remove stale
  // encoding/length metadata below even when the backend ignores this request.
  headers.set("accept-encoding", "identity");
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
    signal: request.signal,
  };
  if (request.method !== "GET" && request.method !== "HEAD" && request.body) {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    const upstream = await fetch(`${getBackendUrl()}${path}${incoming.search}`, init);
    const responseHeaders = endToEndHeaders(upstream.headers);
    if (upstream.body && /^(gzip|deflate|br)$/i.test(responseHeaders.get("content-encoding") || "")) {
      responseHeaders.delete("content-encoding");
      responseHeaders.delete("content-length");
    }
    if (responseHeaders.get("content-type")?.includes("text/event-stream")) {
      responseHeaders.set("cache-control", "no-cache, no-transform");
      responseHeaders.set("x-accel-buffering", "no");
    }
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}
