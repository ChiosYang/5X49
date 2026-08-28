export async function responseError(response: Response, fallback: string) {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  const message = typeof detail === "string"
    ? detail
    : typeof detail?.message === "string"
      ? detail.message
      : fallback;
  return new Error(message);
}

export const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    throw await responseError(res, "API request failed");
  }
  return res.json();
};
