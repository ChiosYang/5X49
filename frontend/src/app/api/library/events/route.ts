const getBackendUrl = () => {
  if (process.env.NODE_ENV === "development") {
    return process.env.BACKEND_URL || process.env.API_URL || "http://127.0.0.1:8000";
  }

  return process.env.BACKEND_URL || process.env.API_URL || "http://backend:8000";
};

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const response = await fetch(`${getBackendUrl()}/library/events`, {
    headers: {
      Accept: "text/event-stream",
    },
    cache: "no-store",
  });

  if (!response.ok || !response.body) {
    return new Response("Failed to connect to library event stream", {
      status: 502,
    });
  }

  return new Response(response.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
