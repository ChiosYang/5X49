import assert from "node:assert/strict";
import { createServer } from "node:http";
import { gzipSync } from "node:zlib";
import test from "node:test";
import { getBackendUrl, proxyBackendRequest } from "./backend-proxy.ts";

test("runtime backend proxy preserves HTTP and streams", async (t) => {
  const old = { BACKEND_URL: process.env.BACKEND_URL, API_URL: process.env.API_URL, NODE_ENV: process.env.NODE_ENV };
  t.after(() => { for (const [key, value] of Object.entries(old)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  } });
  let markStreamClosed;
  const streamClosed = new Promise(resolve => { markStreamClosed = resolve; });
  const server = createServer(async (req, res) => {
    if (req.url === "/library/events") {
      res.on("close", markStreamClosed);
      res.writeHead(200, { "content-type": "text/event-stream" });
      res.write("data: first\n\n");
      return; // Must arrive while the upstream is still open.
    }
    if (req.url === "/compressed") {
      const body = gzipSync("decoded response");
      res.writeHead(200, { "content-encoding": "gzip", "content-length": body.length });
      return res.end(body);
    }
    if (req.url === "/redirect") {
      res.writeHead(307, { location: "/destination" });
      return res.end();
    }
    if (req.url === "/head-media") {
      res.writeHead(200, { "content-length": "1000", "content-type": "video/mp4" });
      return res.end();
    }
    if (req.url === "/conditional") {
      assert.equal(req.headers["if-none-match"], '"synthetic"');
      res.writeHead(304, { etag: '"synthetic"' });
      return res.end();
    }
    if (req.url === "/empty") { res.writeHead(204); return res.end(); }
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    res.writeHead(req.url.startsWith("/media") ? 206 : 422, {
      "content-type": "application/json", "connection": "keep-alive, x-private",
      "x-private": "must-strip", "x-public": "keep", "content-range": "bytes 0-3/10",
      "set-cookie": ["one=1; Path=/", "two=2; Path=/"],
    });
    res.end(JSON.stringify({ path: req.url, method: req.method, headers: req.headers, body: Buffer.concat(chunks).toString() }));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  process.env.BACKEND_URL = `http://127.0.0.1:${server.address().port}/`;
  const request = (path, init) => new Request(`http://frontend${path}`, init);
  for (const method of ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]) {
    const response = await proxyBackendRequest(request("/api/echo/a%20b?x=1&x=2", {
      method, ...(method === "GET" ? {} : { body: "payload" }),
      headers: { authorization: "Bearer synthetic", cookie: "session=synthetic", connection: "x-secret", "x-secret": "strip" },
    }));
    assert.equal(response.status, 422);
    assert.equal(response.headers.get("x-private"), null);
    assert.equal(response.headers.get("connection"), null);
    assert.equal(response.headers.get("x-public"), "keep");
    assert.deepEqual(response.headers.getSetCookie(), ["one=1; Path=/", "two=2; Path=/"]);
    const echo = await response.json();
    assert.equal(echo.method, method);
    assert.equal(echo.path, "/echo/a%20b?x=1&x=2");
    assert.equal(echo.body, method === "GET" ? "" : "payload");
    assert.equal(echo.headers.authorization, "Bearer synthetic");
    assert.equal(echo.headers.cookie, "session=synthetic");
    assert.equal(echo.headers["x-secret"], undefined);
  }
  const media = await proxyBackendRequest(request("/media/movie.mp4", { headers: { range: "bytes=0-3" } }));
  assert.equal(media.status, 206);
  assert.equal(media.headers.get("content-range"), "bytes 0-3/10");
  assert.equal((await media.json()).headers.range, "bytes=0-3");
  const head = await proxyBackendRequest(request("/api/echo", { method: "HEAD" }));
  assert.equal(await head.text(), "");
  const mediaHead = await proxyBackendRequest(request("/api/head-media", { method: "HEAD" }));
  assert.equal(mediaHead.headers.get("content-length"), "1000");
  const conditional = await proxyBackendRequest(request("/api/conditional", { headers: { "if-none-match": '"synthetic"' } }));
  assert.equal(conditional.status, 304);
  assert.equal(conditional.headers.get("etag"), '"synthetic"');
  assert.equal((await proxyBackendRequest(request("/api/empty"))).status, 204);
  const redirect = await proxyBackendRequest(request("/api/redirect"));
  assert.equal(redirect.status, 307);
  assert.equal(redirect.headers.get("location"), "/destination");
  const compressed = await proxyBackendRequest(request("/api/compressed"));
  assert.equal(compressed.headers.get("content-encoding"), null);
  assert.equal(compressed.headers.get("content-length"), null);
  assert.equal(await compressed.text(), "decoded response");
  const controller = new AbortController();
  const stream = await proxyBackendRequest(request("/api/library/events", { signal: controller.signal }));
  assert.equal(stream.headers.get("x-accel-buffering"), "no");
  const reader = stream.body.getReader();
  assert.equal(new TextDecoder().decode((await reader.read()).value), "data: first\n\n");
  controller.abort();
  await reader.cancel().catch(() => {});
  let timeout;
  try {
    await Promise.race([streamClosed, new Promise((_, reject) => {
      timeout = setTimeout(() => reject(new Error("Upstream SSE did not close on abort")), 2000);
    })]);
  } finally { clearTimeout(timeout); }

  // Resolution is per request, not captured at module import/build time.
  process.env.BACKEND_URL = "http://127.0.0.1:1";
  assert.equal((await proxyBackendRequest(request("/api/health"))).status, 502);
  delete process.env.BACKEND_URL;
  process.env.API_URL = "http://legacy:8000/";
  assert.equal(getBackendUrl(), "http://legacy:8000");
  delete process.env.API_URL;
  process.env.NODE_ENV = "development";
  assert.equal(getBackendUrl(), "http://127.0.0.1:8000");
  process.env.NODE_ENV = "production";
  assert.equal(getBackendUrl(), "http://backend:8000");
});
