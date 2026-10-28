export const linear = (d0: number, d1: number, r0: number, r1: number) => (x: number) =>
  d1 === d0 ? (r0 + r1) / 2 : r0 + ((x - d0) / (d1 - d0)) * (r1 - r0)

/** Round-number ticks between lo and hi. */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  const span = hi - lo || Math.abs(hi) || 1
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(+t.toFixed(10))
  return out
}
