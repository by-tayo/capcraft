import { useWidth } from '../lib/hooks'
import { linear, niceTicks } from '../lib/scale'
import { moneyShort } from '../lib/format'

type Props = { edges: number[]; counts: number[]; overflow: number; total: number; goal?: number | null; median: number; invested: number }
const H = 220
const M = { l: 12, r: 12, t: 40, b: 28 }

/** Where the 'final balance' of every simulated future landed. */
export function Histogram({ edges, counts, overflow, total, goal, median, invested }: Props) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const iw = W - M.l - M.r
  const ih = H - M.t - M.b
  const lo = edges[0]
  const hi = edges[edges.length - 1]
  const x = linear(lo, hi, 0, iw)
  const peak = Math.max(...counts, 1)
  const y = linear(0, peak, ih, 0)
  const marks = [
    { v: invested, label: 'You put in', color: 'var(--muted)' },
    { v: median, label: 'Typical', color: 'var(--blue)' },
    ...(goal != null ? [{ v: goal, label: 'Goal', color: 'var(--teal)' }] : []),
  ].filter((m) => m.v >= lo && m.v <= hi)

  return (
    <div className="chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Histogram of final balances across all simulated futures">
        <g transform={`translate(${M.l},${M.t})`}>
          {counts.map((c, i) => {
            const mid = (edges[i] + edges[i + 1]) / 2
            const miss = goal != null && mid < goal
            return (
              <rect key={i} x={x(edges[i]) + 1} width={Math.max(1, x(edges[i + 1]) - x(edges[i]) - 2)} y={y(c)} height={ih - y(c)}
                rx={2} fill={goal == null ? 'var(--blue)' : miss ? 'var(--coral)' : 'var(--teal)'} opacity={0.8}>
                <title>{`${moneyShort(edges[i])} to ${moneyShort(edges[i + 1])}: ${((c / total) * 100).toFixed(1)}% of futures`}</title>
              </rect>
            )
          })}
          <line x1={0} x2={iw} y1={ih} y2={ih} stroke="var(--rule)" />
          <g className="axis">
            {niceTicks(lo, hi, 5).map((t) => <text key={t} x={x(t)} y={ih + 18} textAnchor="middle">{moneyShort(t)}</text>)}
          </g>
          {marks.map((m, i) => (
            <g key={m.label}>
              <line x1={x(m.v)} x2={x(m.v)} y1={-8 - (i % 2) * 16} y2={ih} stroke={m.color} strokeWidth={2} strokeDasharray={m.label === 'Goal' ? '2 3' : undefined} />
              <text x={x(m.v) + 5} y={-11 - (i % 2) * 16} textAnchor="start" fill={m.color} fontSize={12} fontWeight={600}>{m.label}</text>
            </g>
          ))}
        </g>
      </svg>
      {overflow > 0 && <p className="hint">The best {((overflow / total) * 100).toFixed(0)}% of futures end beyond {moneyShort(hi)} and are not drawn.</p>}
    </div>
  )
}
