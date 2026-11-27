/** Seconds as the blotter's age readout. Exported (and pure) because the
    tick's arithmetic is exactly what a render test can pin. */
export function fmtAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 86400) {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    return `${d}d ${h}h`;
  }
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}:${String(m).padStart(2, "0")}h`;
  }
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}
