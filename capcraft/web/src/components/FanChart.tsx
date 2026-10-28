import { useMemo, useState } from 'react'
import { useWidth } from '../lib/hooks'
import { linear, niceTicks } from '../lib/scale'
import { money, moneyShort } from '../lib/format'

type Props = {
  time: number[]
  bands: Record<string, number[]>
  straightLine: number[]
  invested: number[]
  goal?: number | null
  paths: number[][]
  /** 'all' shows every future; 'replay' dims them and draws one path up to `upTo`. */
  mode: 'all' | 'replay'
  replay?: { path: number[]; upTo: number }
}

const H = 380
const M = { l: 58, r: 14, t: 14, b: 30 }

export function FanChart({ time, bands, straightLine, invested, goal, paths, mode, replay }: Props) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const n = time.length
  const iw = W - M.l - M.r
  const ih = H - M.t - M.b

  const { x, y, yTicks, xTicks } = useMemo(() => {
    const top = Math.max(bands.p95[n - 1], straightLine[n - 1], goal ?? 0, ...(replay ? replay.path : []))
    const yMax = niceTicks(0, top * 1.04, 5).at(-1)! || top
    const x = linear(0, time[n - 1], 0, iw)
    const y = linear(0, yMax, ih, 0)
    const years = time[n - 1]
    const step = iw < 420 ? (years <= 20 ? 5 : 10) : years <= 10 ? 1 : years <= 20 ? 2 : years <= 30 ? 5 : 10
    const xTicks: number[] = []
    for (let t = 0; t <= years; t += step) xTicks.push(t)
    return { x, y, yTicks: niceTicks(0, yMax, 5), xTicks }
  }, [time, bands, straightLine, goal, replay, n, iw, ih])

  const line = (v: number[], upTo = n - 1) =>
    v.slice(0, upTo + 1).map((d, i) => `${i ? 'L' : 'M'}${x(time[i]).toFixed(1)},${y(d).toFixed(1)}`).join('')
  const area = (hi: number[], lo: number[]) =>
    line(hi) + [...lo].reverse().map((d, i) => `L${x(time[n - 1 - i]).toFixed(1)},${y(d).toFixed(1)}`).join('') + 'Z'

  const dim = mode === 'replay'
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const t = ((e.clientX - r.left) / r.width) * time[n - 1]
    setHover(Math.min(n - 1, Math.max(0, Math.round((t / time[n - 1]) * (n - 1)))))
  }

  const head = replay ? Math.min(replay.upTo, n - 1) : 0
  const tipLeft = hover == null ? 0 : M.l + x(time[hover])
  const flip = tipLeft > W * 0.62

  return (
    <div className="chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Fan chart of ${paths.length > 0 ? 'simulated' : ''} portfolio value over ${time[n - 1]} years: the middle 50% and middle 90% of outcomes, the straight-line plan, and money put in.`}>
        <g transform={`translate(${M.l},${M.t})`}>
          <g className="grid axis">
            {yTicks.map((t) => (
              <g key={t}>
                <line x1={0} x2={iw} y1={y(t)} y2={y(t)} />
                <text x={-10} y={y(t)} textAnchor="end" dominantBaseline="middle">{moneyShort(t)}</text>
              </g>
            ))}
            {xTicks.map((t) => <text key={t} x={x(t)} y={ih + 20} textAnchor="middle">{t === 0 ? 'Today' : `${t}y`}</text>)}
          </g>

          <g style={{ opacity: dim ? 0.18 : 1, transition: 'opacity .5s' }}>
            <path d={area(bands.p95, bands.p5)} fill="var(--blue)" opacity={0.16} />
            <path d={area(bands.p75, bands.p25)} fill="var(--blue)" opacity={0.28} />
            {mode === 'all' && paths.slice(0, 12).map((p, i) => (
              <path key={i} d={line(p)} fill="none" stroke="var(--blue)" strokeWidth={1} opacity={0.35} />
            ))}
            <path d={line(bands.p50)} fill="none" stroke="var(--blue)" strokeWidth={2.5} strokeLinejoin="round" />
          </g>

          <path d={line(invested)} fill="none" stroke="var(--muted)" strokeWidth={1.5} opacity={0.8} />
          <path d={line(straightLine)} fill="none" stroke="var(--brass)" strokeWidth={2.5} strokeDasharray="7 5" />

          {goal != null && (
            <g>
              <line x1={0} x2={iw} y1={y(goal)} y2={y(goal)} stroke="var(--teal)" strokeWidth={1.5} strokeDasharray="2 4" />
              <text x={iw} y={y(goal) - 6} textAnchor="end" fill="var(--teal)" fontSize={12} fontWeight={600}>Goal {moneyShort(goal)}</text>
            </g>
          )}

          {replay && (
            <g>
              <path d={line(replay.path, head)} fill="none" stroke="var(--accent)" strokeWidth={2.75} strokeLinejoin="round" />
              <circle cx={x(time[head])} cy={y(replay.path[head])} r={5.5} fill="var(--accent)" stroke="var(--ink)" strokeWidth={2} />
            </g>
          )}

          {!replay && hover != null && (
            <g pointerEvents="none">
              <line x1={x(time[hover])} x2={x(time[hover])} y1={0} y2={ih} stroke="var(--muted)" strokeWidth={1} />
              {(['p95', 'p50', 'p5'] as const).map((k) => (
                <circle key={k} cx={x(time[hover])} cy={y(bands[k][hover])} r={4} fill="var(--blue)" stroke="var(--ink)" strokeWidth={2} />
              ))}
              <circle cx={x(time[hover])} cy={y(straightLine[hover])} r={4} fill="var(--brass)" stroke="var(--ink)" strokeWidth={2} />
            </g>
          )}
          <rect x={0} y={0} width={iw} height={ih} fill="transparent"
            onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </g>
      </svg>

      {!replay && hover != null && (
        <div className="tip" style={{ left: flip ? tipLeft - 184 : tipLeft + 14, top: M.t + 8 }}>
          <div className="h">{time[hover] === 0 ? 'Today' : `Year ${time[hover].toFixed(time[hover] % 1 ? 1 : 0)}`}</div>
          <div className="r"><span>Good case (95%)</span><b>{money(bands.p95[hover])}</b></div>
          <div className="r"><span>Typical</span><b>{money(bands.p50[hover])}</b></div>
          <div className="r"><span>Bad case (5%)</span><b>{money(bands.p5[hover])}</b></div>
          <div className="r"><span>Straight line</span><b>{money(straightLine[hover])}</b></div>
          <div className="r"><span>You put in</span><b>{money(invested[hover])}</b></div>
        </div>
      )}

      <div className="legend">
        <span><i className="band" style={{ background: 'var(--blue)', borderTop: 0 }} />Middle 90% of futures</span>
        <span><i style={{ borderColor: 'var(--blue)' }} />Typical (median)</span>
        <span><i className="dash" style={{ borderColor: 'var(--brass)' }} />Straight-line plan</span>
        <span><i style={{ borderColor: 'var(--muted)', borderTopWidth: 2 }} />Money you put in</span>
        {replay && <span><i style={{ borderColor: 'var(--accent)' }} />This one future</span>}
      </div>
    </div>
  )
}
