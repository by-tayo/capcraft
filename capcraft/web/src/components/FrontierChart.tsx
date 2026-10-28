import { useWidth } from '../lib/hooks'
import { linear, niceTicks } from '../lib/scale'
import { pct } from '../lib/format'
import type { XrayResponse } from '../api/client'

type Frontier = NonNullable<XrayResponse['frontier']>
const H = 380
const M = { l: 52, r: 18, t: 14, b: 38 }

/** Risk (across) against return (up) for thousands of random mixes of the holdings. */
export function FrontierChart({ f }: { f: Frontier }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const iw = W - M.l - M.r
  const ih = H - M.t - M.b
  const xs = [...f.points, ...f.assets, f.current].map((p) => p.annual_risk)
  const ys = [...f.points, ...f.assets, f.current].map((p) => p.annual_return)
  const xt = niceTicks(Math.min(...xs) * 0.95, Math.max(...xs) * 1.03, 6)
  const yt = niceTicks(Math.min(...ys) - 0.01, Math.max(...ys) + 0.01, 5)
  const x0 = Math.min(xt[0], Math.min(...xs) - 0.005), x1 = Math.max(xt.at(-1)!, Math.max(...xs) + 0.005)
  const y0 = Math.min(yt[0], Math.min(...ys) - 0.005), y1 = Math.max(yt.at(-1)!, Math.max(...ys) + 0.005)
  const x = linear(x0, x1, 0, iw)
  const y = linear(y0, y1, ih, 0)
  const edge = f.edge.map((p, i) => `${i ? 'L' : 'M'}${x(p.annual_risk)},${y(p.annual_return)}`).join('')
  const lab = (px: number, text: string, py: number, color: string) => (
    <text x={px > iw * 0.8 ? px - 9 : px + 9} y={py + 4} textAnchor={px > iw * 0.8 ? 'end' : 'start'} fill={color} fontSize={12} fontWeight={600}
      style={{ paintOrder: 'stroke', stroke: 'var(--panel)', strokeWidth: 3 }}>{text}</text>
  )
  return (
    <div className="chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Risk and return of thousands of random mixes of your holdings, with your current mix marked">
        <g transform={`translate(${M.l},${M.t})`}>
          <g className="grid axis">
            {yt.map((t) => <g key={t}><line x1={0} x2={iw} y1={y(t)} y2={y(t)} /><text x={-10} y={y(t)} textAnchor="end" dominantBaseline="middle">{pct(t, 0)}</text></g>)}
            {xt.map((t) => <text key={t} x={x(t)} y={ih + 18} textAnchor="middle">{pct(t, 0)}</text>)}
            <text x={iw / 2} y={ih + 34} textAnchor="middle">Risk (yearly standard deviation)</text>
            <text transform={`translate(-42,${ih / 2}) rotate(-90)`} textAnchor="middle">Average yearly return</text>
          </g>
          {f.points.map((p, i) => <circle key={i} cx={x(p.annual_risk)} cy={y(p.annual_return)} r={2.2} fill="var(--blue)" opacity={0.28} />)}
          <path d={edge} fill="none" stroke="var(--blue)" strokeWidth={2.5} />
          {f.assets.map((a) => (
            <g key={a.name}>
              <circle cx={x(a.annual_risk)} cy={y(a.annual_return)} r={5} fill="var(--muted)" stroke="var(--ink)" strokeWidth={2} />
              {lab(x(a.annual_risk), a.name ?? '', y(a.annual_return), 'var(--text)')}
            </g>
          ))}
          <circle cx={x(f.min_variance.annual_risk)} cy={y(f.min_variance.annual_return)} r={6} fill="none" stroke="var(--teal)" strokeWidth={2.5} />
          <circle cx={x(f.max_sharpe.annual_risk)} cy={y(f.max_sharpe.annual_return)} r={6} fill="none" stroke="var(--coral)" strokeWidth={2.5} />
          <path d={`M${x(f.current.annual_risk)},${y(f.current.annual_return) - 9}l8,9l-8,9l-8,-9z`} fill="var(--accent)" stroke="var(--ink)" strokeWidth={2} />
          {lab(x(f.current.annual_risk), 'Your mix', y(f.current.annual_return) - 12, 'var(--accent)')}
        </g>
      </svg>
      <div className="legend">
        <span><i style={{ borderColor: 'var(--blue)' }} />Best return found at each risk level</span>
        <span><i className="band" style={{ background: 'var(--blue)' }} />Random mixes</span>
        <span style={{ color: 'var(--accent)' }}>◆ Your mix</span>
        <span style={{ color: 'var(--teal)' }}>◯ Lowest risk</span>
        <span style={{ color: 'var(--coral)' }}>◯ Best Sharpe</span>
      </div>
    </div>
  )
}
