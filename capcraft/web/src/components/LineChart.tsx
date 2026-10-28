import { useMemo, useState } from 'react'
import { useWidth } from '../lib/hooks'
import { linear, niceTicks } from '../lib/scale'

export type Line = { name: string; values: number[]; color: string; width?: number; dash?: string; area?: boolean }
type Props = {
  labels: string[]
  series: Line[]
  yFormat: (v: number) => string
  height?: number
  zeroLine?: boolean
  label: string
}
const M = { l: 56, r: 14, t: 12, b: 28 }

/** Several series over the same x positions, with a hover crosshair and tooltip. */
export function LineChart({ labels, series, yFormat, height = 300, zeroLine, label }: Props) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const n = labels.length
  const iw = W - M.l - M.r
  const ih = height - M.t - M.b

  const { x, y, ticks } = useMemo(() => {
    const all = series.flatMap((s) => s.values)
    let lo = Math.min(...all, zeroLine ? 0 : Infinity)
    let hi = Math.max(...all, zeroLine ? 0 : -Infinity)
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = 0; hi = 1 }
    const pad = (hi - lo) * 0.05 || 1
    const t = niceTicks(lo - (zeroLine ? 0 : pad), hi + pad, 5)
    return { x: linear(0, n - 1, 0, iw), y: linear(t[0], t.at(-1)!, ih, 0), ticks: t }
  }, [series, n, iw, ih, zeroLine])

  const path = (v: number[]) => v.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d).toFixed(1)}`).join('')
  const xLabelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 80))))
  const flip = hover != null && x(hover) > iw * 0.6

  return (
    <div className="chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label}>
        <g transform={`translate(${M.l},${M.t})`}>
          <g className="grid axis">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={0} x2={iw} y1={y(t)} y2={y(t)} />
                <text x={-10} y={y(t)} textAnchor="end" dominantBaseline="middle">{yFormat(t)}</text>
              </g>
            ))}
            {labels.map((l, i) => i % xLabelEvery === 0 && <text key={i} x={x(i)} y={ih + 20} textAnchor="middle">{l}</text>)}
          </g>
          {series.map((s) => (
            <g key={s.name}>
              {s.area && <path d={`${path(s.values)}L${x(n - 1)},${y(0)}L0,${y(0)}Z`} fill={s.color} opacity={0.22} />}
              <path d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dash} strokeLinejoin="round" />
            </g>
          ))}
          {hover != null && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={0} y2={ih} stroke="var(--muted)" />
              {series.map((s) => <circle key={s.name} cx={x(hover)} cy={y(s.values[hover])} r={3.5} fill={s.color} stroke="var(--ink)" strokeWidth={2} />)}
            </g>
          )}
          <rect x={0} y={0} width={iw} height={ih} fill="transparent"
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              setHover(Math.min(n - 1, Math.max(0, Math.round(((e.clientX - r.left) / r.width) * (n - 1)))))
            }}
            onPointerLeave={() => setHover(null)} />
        </g>
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: flip ? M.l + x(hover) - 190 : M.l + x(hover) + 14, top: M.t + 6 }}>
          <div className="h">{labels[hover]}</div>
          {series.map((s) => (
            <div className="r" key={s.name}>
              <span><i style={{ display: 'inline-block', width: 10, height: 3, background: s.color, marginRight: 6, verticalAlign: 'middle' }} />{s.name}</span>
              <b>{yFormat(s.values[hover])}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
