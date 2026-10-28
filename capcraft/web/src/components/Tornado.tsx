import { useWidth } from '../lib/hooks'
import { linear } from '../lib/scale'
import type { DCFResponse } from '../api/client'

const ROW = 52
const M = { l: 8, r: 8, t: 6, b: 6 }

/** Each bar shows how far the answer moves when ONE assumption goes to its low and high value. */
export function Tornado({ bars, base, fmt }: { bars: DCFResponse['tornado']; base: number; fmt: (v: number) => string }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const iw = Math.max(160, W - M.l - M.r)
  const lo = Math.min(...bars.flatMap((b) => [b.low_output, b.high_output]), base)
  const hi = Math.max(...bars.flatMap((b) => [b.low_output, b.high_output]), base)
  const pad = (hi - lo) * 0.4 || 1
  const x = linear(lo - pad, hi + pad, 0, iw)
  const H = M.t + M.b + ROW * bars.length

  return (
    <div className="chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Tornado chart: how much the value changes when each assumption moves to its low and high setting">
        <g transform={`translate(${M.l},${M.t})`}>
          {bars.map((b, i) => {
            const yy = i * ROW
            const ends = [{ v: b.low_output, t: b.low_label }, { v: b.high_output, t: b.high_label }]
            return (
              <g key={b.param} transform={`translate(0,${yy})`}>
                <text x={0} y={12} fill="var(--text)" fontSize={13} fontWeight={600}>{b.label}</text>
                {ends.map((e) => {
                  const up = e.v >= base
                  const x0 = Math.min(x(base), x(e.v))
                  return (
                    <g key={e.t}>
                      <rect x={x0} y={20} width={Math.max(2, Math.abs(x(e.v) - x(base)))} height={ROW - 28} rx={3} fill={up ? 'var(--teal)' : 'var(--coral)'} opacity={0.85}>
                        <title>{`${b.label} at ${e.t}: ${fmt(e.v)}`}</title>
                      </rect>
                      <text x={up ? x(e.v) + 6 : x(e.v) - 6} y={20 + (ROW - 28) / 2} textAnchor={up ? 'start' : 'end'} dominantBaseline="middle" fill="var(--muted)" fontSize={11.5}>
                        {e.t} · {fmt(e.v)}
                      </text>
                    </g>
                  )
                })}
              </g>
            )
          })}
          <line x1={x(base)} x2={x(base)} y1={0} y2={H - M.t - M.b} stroke="var(--text)" strokeWidth={1.5} />
        </g>
      </svg>
    </div>
  )
}
