import axios from "axios";

// What the backend actually said about a failed request, or `fallback` when it
// said nothing usable.
//
// The backend writes its refusals to be read by a person — "Broker B already
// has a situation on 2026-02-01" — and every call site used to throw them away
// in a bare `catch { setError("Save failed.") }`. The reader got a sentence
// naming the verb and nothing else, and so did whoever was debugging. The
// fallback is what we say when there is genuinely nothing better, not the
// first thing we reach for.
export function apiError(e: unknown, fallback: string): string {
  if (!axios.isAxiosError(e)) return fallback;

  // Nothing answered at all. "The server refused this" and "there was no
  // server" are different claims, and reporting the second as the first sends
  // someone off to correct a request that was fine — the same distinction the
  // backend keeps between MarketUnreachable and PriceError.
  if (!e.response) return "The backend did not answer. Is it running on :8000?";

  const detail = (e.response.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();

  // 422: FastAPI validates the body and returns one entry per offending field.
  // String()-ing that array reads "[object Object]", which is a worse message
  // than the fallback it replaced — so it is unpacked rather than stringified.
  if (Array.isArray(detail)) {
    const fields = detail
      .map((d) => {
        const { loc, msg } = d as { loc?: unknown[]; msg?: unknown };
        if (typeof msg !== "string") return null;
        const field = Array.isArray(loc) && loc.length ? String(loc[loc.length - 1]) : null;
        return field ? `${field}: ${msg}` : msg;
      })
      .filter((line): line is string => line !== null);
    if (fields.length) return fields.join("; ");
  }

  // A 500 comes back as plain "Internal Server Error" with no detail, which
  // names the failure no better than the caller's own fallback does.
  return fallback;
}
