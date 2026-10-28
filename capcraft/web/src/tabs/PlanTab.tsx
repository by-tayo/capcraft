import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type Meta, type PlanRequest, type PlanResponse } from '../api/client'
import { FanChart } from '../components/FanChart'
import { NumberField, SliderField } from '../components/Field'
import { Histogram } from '../components/Histogram'
import { useDebounced, usePrefersReducedMotion } from '../lib/hooks'
import { useApiQuery } from '../lib/useApiQuery'
import { money, moneyShort, outOfTen, pct } from '../lib/format'

const DEFAULTS = { initial: 10000, monthly: 500, years: 20, ret: 0.07, vol: 0.15, goal: 400000, n: 5000 }

export function PlanTab({ meta }: { meta: Meta | null }) {
  const [f, setF] = useState(DEFAULTS)
  const [seed, setSeed] = useState(7)
  const req: PlanRequest = useMemo(() => ({
    initial: f.initial, monthly_contribution: f.monthly, years: f.years, expected_return: f.ret,
    volatility: f.vol, goal: f.goal > 0 ? f.goal : null, n_sims: f.n, seed,
  }), [f, seed])
  const valid = Object.values(f).every(Number.isFinite)
  const debounced = useDebounced(req, 350)

  const { data, error, busy } = useApiQuery(valid ? debounced : null, api.plan)

  const set = <K extends keyof typeof DEFAULTS>(k: K) => (v: number) => setF((p) => ({ ...p, [k]: v }))

  return (
    <div className="work">
      <aside className="controls" aria-label="Plan inputs">
        <h2>Your plan</h2>
        <NumberField label="Invested today" prefix="$" value={f.initial} onChange={set('initial')} min={0} max={1e9} step={1000} />
        <NumberField label="Added each month" prefix="$" value={f.monthly} onChange={set('monthly')} min={0} max={1e7} step={50} />
        <NumberField label="Years" value={f.years} onChange={set('years')} min={1} max={50} />
        <NumberField label="Goal (optional)" prefix="$" value={f.goal} onChange={set('goal')} min={0} step={10000} hint="Leave at 0 to skip." />
        <SliderField label="Average yearly return" value={f.ret} onChange={set('ret')} min={0} max={0.15} step={0.005} format={(v) => pct(v)}
          hint="What you expect on average. Real returns will not be this smooth." />
        <SliderField label="Ups and downs (volatility)" value={f.vol} onChange={set('vol')} min={0} max={0.5} step={0.01} format={(v) => pct(v, 0)}
          hint="Typical yearly swing. Around 15% fits a broad stock fund; 5% a bond fund." />
        <div className="field">
          <span className="label">Random draw <span className="value">#{seed}</span></span>
          <div className="row">
            <button className="btn" onClick={() => setSeed(Math.floor(Math.random() * 1e6))}>Draw new futures</button>
          </div>
          <span className="hint">The same number always gives the same futures, so moving a slider changes only your assumptions, not the luck.</span>
        </div>
      </aside>

      <main className={`results ${busy ? 'loading' : ''}`}>
        {error && <div className="error" role="alert">{error}</div>}
        {!data && !error && <div className="status">Running 5,000 futures…</div>}
        {data && <PlanResults key={`${data.seed}-${data.years}`} d={data} sims={f.n} meta={meta} />}
      </main>
    </div>
  )
}

function PlanResults({ d, sims, meta }: { d: PlanResponse; sims: number; meta: Meta | null }) {
  const reduced = usePrefersReducedMotion()
  const [view, setView] = useState<'all' | 'replay'>('all')
  const [pick, setPick] = useState(0)
  const [upTo, setUpTo] = useState(0)
  const [playing, setPlaying] = useState(false)
  const raf = useRef(0)
  const nSteps = d.time.length - 1

  const putIn = useMemo(() => {
    const monthly = (d.invested - d.straight_line[0]) / nSteps
    return d.time.map((_, i) => d.straight_line[0] + monthly * i)
  }, [d, nSteps])

  useEffect(() => {
    if (!playing) return
    if (reduced) { setUpTo(nSteps); setPlaying(false); return }
    let last: number | null = null
    let pos = upTo
    const perMs = nSteps / 9000 // the whole run takes about nine seconds
    const tick = (now: number) => {
      pos = Math.min(nSteps, Math.max(0, pos + (last === null ? 0 : now - last) * perMs))
      last = now
      setUpTo(pos)
      if (pos >= nSteps) setPlaying(false)
      else raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, nSteps, reduced])

  const start = (k: number) => {
    setPick(k); setUpTo(0); setView('replay'); setPlaying(true)
  }
  const path = d.sample_paths[pick % d.sample_paths.length]
  const idx = Math.min(nSteps, Math.floor(upTo))
  const yr = Math.floor(idx / 12)
  const mo = idx % 12
  const done = view === 'replay' && idx >= nSteps

  const goal = d.goal
  const headline = goal != null && d.prob_goal != null
    ? <>In <b>{outOfTen(d.prob_goal)}</b> simulated futures you reach {money(goal)}.</>
    : <>Half of simulated futures end above <b>{money(d.median_final)}</b>.</>
  const need = d.needed_monthly?.find((n) => n.confidence === 0.8)

  return (
    <>
      <div className="verdict">
        <h1>{headline}</h1>
        <p>
          Straight-line math says you end with {money(d.straight_line_final)}, but {pct(d.share_below_straight_line, 0)} of futures finish below that.
          Ups and downs cost you: the typical outcome ({money(d.median_final)}) sits under the average ({money(d.mean_final)}).
          {need && goal != null && <> To reach the goal in 8 of 10 futures, you would add about <b style={{ color: 'var(--text)' }}>{money(need.monthly)}</b> a month.</>}
        </p>
      </div>

      <section className="card" aria-label="Fan chart">
        <h2>{view === 'replay' ? 'Live one future' : `${sims.toLocaleString()} possible futures`}</h2>
        <p className="sub">
          {view === 'replay'
            ? 'This is one random path through the same assumptions. Your plan rarely follows the straight line.'
            : 'The shaded bands hold the middle 50% and 90% of outcomes. Hover to read any year.'}
        </p>
        <div className="replaybar">
          {view === 'all' ? (
            <button className="btn primary" onClick={() => start(pick)}>Live one future</button>
          ) : (
            <>
              <button className="btn" onClick={() => (done ? start(pick) : setPlaying((p) => !p))}>{done ? 'Replay' : playing ? 'Pause' : 'Resume'}</button>
              <button className="btn" onClick={() => start(pick + 1)}>Another future</button>
              <button className="btn primary" onClick={() => { setPlaying(false); setView('all') }}>Zoom out to all futures</button>
              <span className="readout" aria-live="off">
                Year <b>{yr}</b>, month <b>{mo}</b>: balance <b>{money(path[idx])}</b>, you put in <b>{money(putIn[idx])}</b>
                {goal != null && done && <> · {path[nSteps] >= goal ? <b style={{ color: 'var(--teal)' }}>Reached the goal</b> : <b style={{ color: 'var(--coral)' }}>Missed the goal</b>}</>}
              </span>
            </>
          )}
        </div>
        <FanChart time={d.time} bands={d.bands} straightLine={d.straight_line} invested={putIn} goal={goal}
          paths={d.sample_paths} mode={view} replay={view === 'replay' ? { path, upTo: idx } : undefined} />
      </section>

      <div className="stats">
        <Stat k="Bad case (5%)" v={money(d.percentiles['5'])} n="1 in 20 futures end lower" />
        <Stat k="Typical (median)" v={money(d.percentiles['50'])} n="Half end lower, half higher" />
        <Stat k="Good case (95%)" v={money(d.percentiles['95'])} n="1 in 20 futures end higher" />
        <Stat k="Chance of ending below what you put in" v={pct(d.prob_loss)} n={`You put in ${money(d.invested)}`} />
      </div>

      <div className="grid2">
        <section className="card">
          <h2>Where the futures end</h2>
          <p className="sub">Each bar counts futures with a final balance in that range.</p>
          <Histogram edges={d.histogram.edges} counts={d.histogram.counts} overflow={d.histogram.overflow} total={d.n_sims}
            goal={goal} median={d.median_final} invested={d.invested} />
        </section>
        <section className="card">
          <h2>{d.needed_monthly ? 'What it takes to reach your goal' : 'Add a goal'}</h2>
          {d.needed_monthly ? (
            <>
              <p className="sub">Monthly amount that reaches {moneyShort(goal!)} in at least this share of futures, under the same assumptions.</p>
              <table className="t">
                <thead><tr><th>Reached in</th><th>Add per month</th><th>Total put in</th></tr></thead>
                <tbody>
                  {d.needed_monthly.map((n) => (
                    <tr key={n.confidence}>
                      <td>{outOfTen(n.confidence)} futures</td><td>{money(n.monthly)}</td>
                      <td>{money(d.straight_line[0] + n.monthly * nSteps)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="hint" style={{ marginTop: 10 }}>
                Compare with your {money((d.invested - d.straight_line[0]) / nSteps)} a month now. Higher confidence costs more because the unlucky futures need a bigger cushion.
              </p>
            </>
          ) : <p className="sub">Enter a goal on the left to see the chance of reaching it and the monthly amount that makes it likely.</p>}
        </section>
      </div>

      <section className="card">
        <details className="assume">
          <summary>Show the chart as a table</summary>
          <div style={{ overflowX: 'auto', marginTop: 12 }}>
            <table className="t">
              <thead><tr><th>Year</th><th>Bad case (5%)</th><th>Typical</th><th>Good case (95%)</th><th>Straight line</th><th>You put in</th></tr></thead>
              <tbody>
                {d.time.map((t, i) => (i % 12 === 0 ? (
                  <tr key={t}><td>{t}</td><td>{money(d.bands.p5[i])}</td><td>{money(d.bands.p50[i])}</td><td>{money(d.bands.p95[i])}</td><td>{money(d.straight_line[i])}</td><td>{money(putIn[i])}</td></tr>
                ) : null))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="card">
        <details className="assume">
          <summary>How this works, and what it leaves out</summary>
          <ul className="notes" style={{ marginTop: 12 }}>
            {(meta?.assumptions.plan ?? []).map((a) => <li key={a}>{a}</li>)}
            <li>Draw #{d.seed}, {d.n_sims.toLocaleString()} futures. {meta?.disclaimer}</li>
          </ul>
        </details>
      </section>
    </>
  )
}

function Stat({ k, v, n }: { k: string; v: string; n: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="v">{v}</div><div className="n">{n}</div></div>
}
