import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, type Meta, type XrayRequest, type XrayResponse } from '../api/client'
import { FrontierChart } from '../components/FrontierChart'
import { LineChart, type Line } from '../components/LineChart'
import { NumberField, SliderField } from '../components/Field'
import { useDebounced } from '../lib/hooks'
import { useApiQuery } from '../lib/useApiQuery'
import { priceColumns } from '../lib/csv'
import { num, pct } from '../lib/format'

const ASSET_COLORS = ['var(--blue)', 'var(--teal)', 'var(--coral)', '#9b87d6', '#6fb1c9', '#c9a96f', '#7fbf7a', '#d48fb0']

export function XrayTab({ meta }: { meta: Meta | null }) {
  const [csv, setCsv] = useState('')
  const [amounts, setAmounts] = useState<Record<string, number>>({})
  const [benchmark, setBenchmark] = useState('')
  const [ppy, setPpy] = useState(12)
  const [rf, setRf] = useState(0.03)
  const [synthetic, setSynthetic] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadSample = () =>
    api.xraySample().then((s) => {
      setLoadError(null); setCsv(s.csv_text); setAmounts(Object.fromEntries(Object.entries(s.amounts).map(([k, v]) => [k, Math.round(v * 10000)]))); setBenchmark(s.benchmark); setSynthetic(s.synthetic); setPpy(12)
    }).catch((e) => setLoadError(e instanceof ApiError ? e.message : String(e)))
  useEffect(() => { loadSample() }, [])

  const columns = useMemo(() => priceColumns(csv), [csv])
  const assets = useMemo(() => columns.filter((c) => c !== benchmark), [columns, benchmark])

  const onCsv = (text: string) => {
    setCsv(text); setSynthetic(false)
    const cols = priceColumns(text)
    setAmounts((prev) => Object.fromEntries(cols.map((c) => [c, prev[c] ?? 1])))
    setBenchmark((b) => (cols.includes(b) ? b : ''))
  }

  const req: XrayRequest | null = useMemo(() => {
    if (!csv || !assets.length) return null
    return {
      csv_text: csv, benchmark: benchmark || null, periods_per_year: ppy, risk_free_annual: rf, n_frontier: 3000, seed: 1,
      amounts: Object.fromEntries(assets.map((a) => [a, Number.isFinite(amounts[a]) ? amounts[a] : 0])),
    }
  }, [csv, assets, amounts, benchmark, ppy, rf])
  const debounced = useDebounced(req, 450)

  const { data, error: apiError, busy } = useApiQuery(debounced, api.xray)
  const error = apiError ?? loadError

  return (
    <div className="work">
      <aside className="controls" aria-label="Portfolio inputs">
        <h2>Your holdings</h2>
        <div className="field">
          <label htmlFor="csv">Price history (CSV)</label>
          <textarea id="csv" className="input" value={csv} spellCheck={false} onChange={(e) => onCsv(e.target.value)} />
          <span className="hint">One column per asset, one row per period. An optional first column of dates is fine.</span>
          <div className="row">
            <button className="btn" onClick={loadSample}>Use sample data</button>
            <label className="btn" style={{ cursor: 'pointer' }}>
              Upload CSV
              <input type="file" accept=".csv,text/csv,text/plain" hidden onChange={async (e) => { const t = await e.target.files?.[0]?.text(); if (t) onCsv(t) }} />
            </label>
          </div>
          {synthetic && <span className="chip">Sample data is made up, not real assets</span>}
        </div>
        <div className="field">
          <label htmlFor="bm">Market benchmark (for beta)</label>
          <select id="bm" className="input" value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
            <option value="">None</option>
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="field">
          <span className="label">Amount in each holding</span>
          {assets.map((a) => (
            <NumberField key={a} label={a} prefix="$" value={amounts[a] ?? 1} min={0} step={100}
              onChange={(v) => setAmounts((p) => ({ ...p, [a]: v }))} />
          ))}
          <span className="hint">Only the proportions matter. Weights are worked out for you.</span>
        </div>
        <div className="field">
          <label htmlFor="ppy">How often the prices are recorded</label>
          <select id="ppy" className="input" value={ppy} onChange={(e) => setPpy(Number(e.target.value))}>
            <option value={12}>Monthly</option><option value={52}>Weekly</option><option value={252}>Daily</option>
            <option value={4}>Quarterly</option><option value={1}>Yearly</option>
          </select>
        </div>
        <SliderField label="Risk-free rate (yearly)" value={rf} onChange={setRf} min={0} max={0.08} step={0.0025} format={(v) => pct(v, 2)}
          hint="What cash earns. Used for Sharpe and Sortino." />
      </aside>

      <main className={`results ${busy ? 'loading' : ''}`}>
        {error && <div className="error" role="alert">{error}</div>}
        {!data && !error && <div className="status">Loading the sample portfolio…</div>}
        {data && <XrayResults d={data} meta={meta} synthetic={synthetic} />}
      </main>
    </div>
  )
}

function XrayResults({ d, meta, synthetic }: { d: XrayResponse; meta: Meta | null; synthetic: boolean }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const m = d.metrics
  const colorOf = (name: string, i: number) => (name === 'Portfolio' ? 'var(--accent)' : ASSET_COLORS[i % ASSET_COLORS.length])
  const lines: Line[] = d.growth.map((s, i) => ({
    name: s.name, values: s.values, color: i === 0 ? 'var(--accent)' : d.metrics.beta_vs_benchmark != null && i === d.growth.length - 1 ? 'var(--muted)' : colorOf(s.name, i - 1),
    width: i === 0 ? 3 : 1.75, dash: d.metrics.beta_vs_benchmark != null && i === d.growth.length - 1 ? '5 4' : undefined,
  }))
  const shown = lines.filter((l) => !hidden.has(l.name))
  const toggle = (n: string) => setHidden((h) => { const x = new Set(h); if (x.has(n)) x.delete(n); else x.add(n); return x })

  const heavy = [...d.assets].sort((a, b) => (b.own_risk_share - b.weight) - (a.own_risk_share - a.weight))[0]
  const years = d.n_periods / d.periods_per_year

  return (
    <>
      <div className="verdict">
        <h1>{m.annualized_return != null ? <>Your mix grew <b>{pct(m.annualized_return)}</b> a year with <b>{pct(m.annualized_volatility)}</b> risk.</> : <>Your mix carries <b>{pct(m.annualized_volatility)}</b> yearly risk.</>}</h1>
        <p>
          {d.diversified
            ? <>Holding these together cut yearly risk by {(d.diversification_benefit * 100).toFixed(1)} percentage points compared with the average holding on its own.</>
            : <>This mix is not reducing risk compared with its holdings on their own.</>}
          {heavy && heavy.own_risk_share - heavy.weight > 0.05 && <> {heavy.name} is {pct(heavy.weight, 0)} of your money but {pct(heavy.own_risk_share, 0)} of your risk.</>}
          {' '}Based on {d.n_periods} periods ({years.toFixed(1)} years).{synthetic && ' This is made-up sample data.'}
        </p>
      </div>

      {d.warnings.filter((w) => !w.startsWith('The frontier plots')).map((w) => <div className="error" key={w} role="status">{w}</div>)}

      <div className="stats">
        <Stat k="Sharpe ratio" v={num(m.sharpe_ratio)} n="Return above cash per unit of risk" />
        <Stat k="Worst drop" v={pct(m.max_drawdown)} n={m.max_drawdown_recovery_index == null ? 'Not recovered yet' : `Recovered by period ${m.max_drawdown_recovery_index}`} />
        <Stat k="Beta" v={num(m.beta_vs_benchmark)} n={m.beta_vs_benchmark == null ? 'Pick a benchmark' : 'Moves this much per 1 for the market'} />
        <Stat k={`Bad ${d.periods_per_year === 12 ? 'month' : 'period'} (95%)`} v={pct(m.historical_var)} n="Loss exceeded in 1 of 20 periods" />
      </div>

      <section className="card">
        <h2>Growth of 100</h2>
        <p className="sub">What 100 invested at the start would have become. Click a name to hide or show it.</p>
        <LineChart labels={d.labels} series={shown} yFormat={(v) => v.toFixed(0)} label="Growth of 100 for the portfolio, each holding and the benchmark" />
        <div className="legend">
          {lines.map((l) => (
            <button key={l.name} className="btn" style={{ padding: '3px 10px', opacity: hidden.has(l.name) ? 0.45 : 1 }} aria-pressed={!hidden.has(l.name)} onClick={() => toggle(l.name)}>
              <i className={l.dash ? 'dash' : ''} style={{ borderColor: l.color }} />{l.name}
            </button>
          ))}
        </div>
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Drops from a previous high</h2>
          <p className="sub">How far below its best value the portfolio sat at each point.</p>
          <LineChart labels={d.labels} height={240} zeroLine yFormat={(v) => pct(v, 0)} label="Portfolio drawdown over time"
            series={[{ name: 'Drawdown', values: d.drawdown, color: 'var(--coral)', area: true }]} />
        </section>
        <section className="card">
          <h2>How the holdings move together</h2>
          <p className="sub">Correlation: 1 moves in step, 0 unrelated, below 0 moves opposite.</p>
          <Heatmap names={d.correlation.names} matrix={d.correlation.matrix} />
        </section>
      </div>

      <section className="card">
        <h2>Holding by holding</h2>
        <p className="sub">Own risk share is the part of the portfolio's risk each holding adds, including how it moves with the others.</p>
        <div style={{ overflowX: 'auto' }}>
          <table className="t">
            <thead><tr><th>Holding</th><th>Weight</th><th>Yearly return</th><th>Yearly risk</th><th>Sharpe</th><th>Worst drop</th><th>Beta</th><th>Share of risk</th></tr></thead>
            <tbody>
              {d.assets.map((a) => (
                <tr key={a.name}>
                  <td>{a.name}</td><td>{pct(a.weight, 0)}</td><td>{pct(a.annual_return)}</td><td>{pct(a.annual_risk)}</td>
                  <td>{num(a.sharpe)}</td><td>{pct(a.max_drawdown, 0)}</td><td>{num(a.beta)}</td>
                  <td><span style={{ display: 'inline-block', height: 8, width: `${Math.max(2, a.own_risk_share * 80)}px`, background: 'var(--blue)', borderRadius: 2, marginRight: 8, verticalAlign: 'middle' }} />{pct(a.own_risk_share, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {d.frontier && (
        <section className="card">
          <h2>Could a different mix have done better?</h2>
          <p className="sub">Each dot is a random mix of the same holdings, scored on this history. This shows what would have worked, not what will.</p>
          <FrontierChart f={d.frontier} />
          <div className="grid2" style={{ marginTop: 14 }}>
            <Mix title="Lowest risk found" mix={d.frontier.min_variance} />
            <Mix title="Best Sharpe found" mix={d.frontier.max_sharpe} />
          </div>
          <p className="hint" style={{ marginTop: 10 }}>The best-Sharpe mix is usually concentrated and fragile: it is tuned to the past. Treat it as a question to ask, not advice. {d.frontier.n_sampled.toLocaleString()} mixes sampled, draw #{d.seed}.</p>
        </section>
      )}

      <section className="card">
        <details className="assume">
          <summary>How this works, and what it leaves out</summary>
          <ul className="notes" style={{ marginTop: 12 }}>
            {(meta?.assumptions.xray ?? []).map((a) => <li key={a}>{a}</li>)}
            {d.warnings.filter((w) => w.startsWith('The frontier plots')).map((w) => <li key={w}>{w}</li>)}
            <li>{meta?.disclaimer}</li>
          </ul>
        </details>
      </section>
    </>
  )
}

function Stat({ k, v, n }: { k: string; v: string; n: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="v">{v}</div><div className="n">{n}</div></div>
}

function Mix({ title, mix }: { title: string; mix: NonNullable<XrayResponse['frontier']>['min_variance'] }) {
  return (
    <div>
      <h2 style={{ fontSize: 14 }}>{title}</h2>
      <p className="hint">{pct(mix.annual_return)} return, {pct(mix.annual_risk)} risk, Sharpe {num(mix.sharpe)}</p>
      <p style={{ fontSize: 14, marginTop: 4 }}>{Object.entries(mix.weights).filter(([, w]) => w >= 0.005).sort((a, b) => b[1] - a[1]).map(([n, w]) => `${n} ${pct(w, 0)}`).join(', ')}</p>
    </div>
  )
}

function Heatmap({ names, matrix }: { names: string[]; matrix: number[][] }) {
  // Diverging: blue for moving together, coral for moving apart, neutral at 0.
  const bg = (v: number) => (v >= 0 ? `color-mix(in srgb, var(--blue) ${Math.round(v * 70)}%, var(--panel))` : `color-mix(in srgb, var(--coral) ${Math.round(-v * 70)}%, var(--panel))`)
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="t" style={{ tableLayout: 'fixed', minWidth: 60 + names.length * 62 }}>
        <thead><tr><th style={{ width: 70 }} />{names.map((n) => <th key={n} style={{ fontSize: 12 }}>{n}</th>)}</tr></thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={names[i]}>
              <td style={{ color: 'var(--muted)', fontSize: 12 }}>{names[i]}</td>
              {row.map((v, j) => <td key={j} style={{ background: bg(v), textAlign: 'center', borderRadius: 4 }} title={`${names[i]} and ${names[j]}: ${v.toFixed(2)}`}>{v.toFixed(2)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
