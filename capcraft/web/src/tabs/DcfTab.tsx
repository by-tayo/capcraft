import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, type CompanyResponse, type DCFRequest, type DCFResponse, type Meta } from '../api/client'
import { NumberField, SliderField } from '../components/Field'
import { Tornado } from '../components/Tornado'
import { useDebounced } from '../lib/hooks'
import { useApiQuery } from '../lib/useApiQuery'
import { num, pct } from '../lib/format'

// Cedar Co is made up. Figures are in millions except per-share amounts.
const DEFAULTS = {
  revenue: 1000, growth: 0.08, years: 5, margin: 0.18, tax: 0.25, da: 0.04, capex: 0.05, nwc: 0.1,
  wacc: 0.09, method: 'gordon' as 'gordon' | 'exit_multiple', tg: 0.025, multiple: 10, debt: 200, shares: 100, price: 20,
}
const usd = (v: number) => `$${v.toFixed(2)}`
const mm = (v: number) => `$${Math.round(v).toLocaleString('en-US')}M`

export function DcfTab({ meta }: { meta: Meta | null }) {
  const [f, setF] = useState(DEFAULTS)
  const [canLoad, setCanLoad] = useState(false)
  const [saved, setSaved] = useState<string[]>([])
  const [ticker, setTicker] = useState('')
  const [company, setCompany] = useState<CompanyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  useEffect(() => { api.capabilities().then((c) => { setCanLoad(c.company); setSaved(c.saved_companies) }).catch(() => setCanLoad(false)) }, [])

  const loadCompany = async (symbol = ticker) => {
    if (!symbol.trim()) return
    setTicker(symbol.toUpperCase())
    setLoading(true); setLoadError(null)
    try {
      const c = await api.company(symbol.trim())
      const a = c.assumptions
      const r = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d
      setF((p) => ({
        ...p, revenue: r(a.base_revenue, 1), growth: r(a.revenue_growth, 3), margin: r(a.ebit_margin, 3), tax: r(a.tax_rate, 3),
        da: r(a.da_pct, 4), capex: r(a.capex_pct, 4), nwc: r(a.nwc_pct, 3), debt: r(a.net_debt, 1), shares: r(a.shares_outstanding, 1),
        price: c.price ? r(c.price.value, 2) : 0, // never keep the old company's price
      }))
      setCompany(c)
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e))
    } finally { setLoading(false) }
  }
  const name = company?.name ?? 'Cedar Co'

  const set = <K extends keyof typeof DEFAULTS>(k: K) => (v: (typeof DEFAULTS)[K]) => setF((p) => ({ ...p, [k]: v }))

  const req: DCFRequest = useMemo(() => ({
    base_revenue: f.revenue, revenue_growth: f.growth, years: f.years, ebit_margin: f.margin, tax_rate: f.tax,
    da_pct: f.da, capex_pct: f.capex, nwc_pct: f.nwc, discount_rate: f.wacc, terminal_method: f.method,
    terminal_growth: f.method === 'gordon' ? f.tg : null, exit_multiple: f.method === 'exit_multiple' ? f.multiple : null,
    net_debt: f.debt, shares_outstanding: f.shares, mid_year: false, market_price: f.price > 0 ? f.price : null,
  }), [f])
  const valid = [f.revenue, f.years, f.debt, f.shares, f.price, f.multiple].every(Number.isFinite)
  const debounced = useDebounced(req, 350)

  const { data, error, busy } = useApiQuery(valid ? debounced : null, api.dcf)

  return (
    <div className="work">
      <aside className="controls" aria-label="Company assumptions">
        <h2>{name} <span className="chip">{company ? `SEC filings FY ${company.fiscal_year_end.slice(0, 4)}${company.source === 'saved' ? `, saved ${company.saved_on}` : ''}` : 'made-up company'}</span></h2>
        {canLoad && (
          <div className="field">
            <label htmlFor="tk">Load a real company by ticker</label>
            <div className="row">
              <input id="tk" className="input" style={{ flex: 1, minWidth: 0 }} value={ticker} placeholder="MSFT" maxLength={10}
                onChange={(e) => setTicker(e.target.value.toUpperCase())} onKeyDown={(e) => e.key === 'Enter' && loadCompany()} />
              <button className="btn" disabled={loading || !ticker.trim()} onClick={() => loadCompany()}>{loading ? 'Loading…' : 'Load'}</button>
            </div>
            {saved.length > 0 && (
              <div className="row" aria-label="Saved companies">
                <span className="hint">Saved:</span>
                {saved.map((t) => <button key={t} className="btn" style={{ padding: '2px 10px' }} onClick={() => loadCompany(t)}>{t}</button>)}
              </div>
            )}
            {loadError && <div className="error" role="alert">{loadError}</div>}
            {company && (
              <details className="assume">
                <summary style={{ fontSize: 13 }}>Where these numbers came from</summary>
                <ul className="notes" style={{ marginTop: 8 }}>
                  {company.provenance.map((p) => <li key={p.field}><b style={{ color: 'var(--text)' }}>{p.field}:</b> {p.how}</li>)}
                  {company.price && <li><b style={{ color: 'var(--text)' }}>Price:</b> ${company.price.value.toFixed(2)} as of {company.price.as_of}.</li>}
                  {company.warnings.map((w) => <li key={w} style={{ color: '#f3b9b1' }}>{w}</li>)}
                </ul>
              </details>
            )}
            <span className="hint">Growth is the company's own past growth, not a forecast. Edit anything.</span>
          </div>
        )}
        <p className="hint">Dollar amounts are in millions, except price per share. {company ? 'Everything below can be edited.' : "Replace every number with your own company's."}</p>
        <NumberField label="Revenue last year ($M)" prefix="$" value={f.revenue} onChange={set('revenue')} min={1} step={50} />
        <SliderField label="Revenue growth, each year" value={f.growth} onChange={set('growth')} min={-0.05} max={0.3} step={0.005} format={(v) => pct(v)} />
        <NumberField label="Forecast years" value={f.years} onChange={set('years')} min={1} max={15} />
        <SliderField label="Operating margin" value={f.margin} onChange={set('margin')} min={0.02} max={0.5} step={0.005} format={(v) => pct(v)} hint="Operating profit (EBIT) as a share of revenue." />
        <SliderField label="Tax rate" value={f.tax} onChange={set('tax')} min={0} max={0.45} step={0.005} format={(v) => pct(v)} />
        <SliderField label="Depreciation, % of revenue" value={f.da} onChange={set('da')} min={0} max={0.15} step={0.0025} format={(v) => pct(v)} />
        <SliderField label="Capital spending, % of revenue" value={f.capex} onChange={set('capex')} min={0} max={0.2} step={0.0025} format={(v) => pct(v)} />
        <SliderField label="Working capital, % of revenue" value={f.nwc} onChange={set('nwc')} min={0} max={0.4} step={0.005} format={(v) => pct(v)} />
        <SliderField label="Discount rate" value={f.wacc} onChange={set('wacc')} min={0.04} max={0.18} step={0.0025} format={(v) => pct(v, 2)}
          hint="The return investors demand for the risk (often WACC)." />
        <div className="field">
          <label htmlFor="tm">Value after the forecast</label>
          <select id="tm" className="input" value={f.method} onChange={(e) => set('method')(e.target.value as 'gordon' | 'exit_multiple')}>
            <option value="gordon">Cash flow grows forever (Gordon)</option>
            <option value="exit_multiple">Sold at a multiple of EBITDA</option>
          </select>
        </div>
        {f.method === 'gordon'
          ? <SliderField label="Growth forever" value={f.tg} onChange={set('tg')} min={0} max={0.05} step={0.0025} format={(v) => pct(v, 2)} hint="Keep this below the long-run growth of the economy." />
          : <NumberField label="Exit multiple (x EBITDA)" value={f.multiple} onChange={set('multiple')} min={1} max={60} step={0.5} />}
        <NumberField label="Net debt ($M)" prefix="$" value={f.debt} onChange={set('debt')} step={50} hint="Debt minus cash. Negative if the company holds net cash." />
        <NumberField label="Shares outstanding (M)" value={f.shares} onChange={set('shares')} min={0.1} step={5} />
        <NumberField label="Market price per share" prefix="$" value={f.price} onChange={set('price')} min={0} step={1} hint={f.price > 0 ? "Set to 0 to skip the reverse DCF." : "Enter the current price to see what the market is assuming."} />
      </aside>

      <main className={`results ${busy ? 'loading' : ''}`}>
        {error && <div className="error" role="alert">{error}</div>}
        {!data && !error && <div className="status">Valuing {name}…</div>}
        {data && <DcfResults d={data} f={f} meta={meta} name={name} />}
      </main>
    </div>
  )
}

function DcfResults({ d, f, meta, name }: { d: DCFResponse; f: typeof DEFAULTS; meta: Meta | null; name: string }) {
  const v = d.valuation
  const r = d.reverse
  const price = r?.market_price
  const per = d.metric === 'value_per_share'
  const fmt = per ? usd : mm

  let headline
  if (r && r.implied_growth.available && r.implied_growth.value != null) {
    const g = r.implied_growth.value
    headline = <>At {usd(r.market_price)}, the market is assuming <b>{pct(g)}</b> revenue growth a year for {f.years} years. You assumed {pct(r.model_average_growth)}.</>
  } else if (r) {
    headline = <>Your assumptions value {name} at <b>{usd(r.model_value)}</b> a share, against a price of {usd(r.market_price)}.</>
  } else {
    headline = <>Your assumptions value {name} at <b>{per ? usd(v.value_per_share!) : fmt(v.equity_value)}</b>{per ? ' a share' : ''}.</>
  }

  const termShare = v.terminal_share
  return (
    <>
      <div className="verdict">
        <h1>{headline}</h1>
        <p>
          {r && <>Your model gives {usd(r.model_value)} a share, {r.upside >= 0 ? `${pct(r.upside, 0)} above` : `${pct(-r.upside, 0)} below`} the price. </>}
          {termShare != null && <>{pct(termShare, 0)} of the value comes from after the forecast ends, so the result leans on that guess.</>}
          {r && !r.implied_growth.available && <> No growth rate between -30% and 60% reproduces the price: {r.implied_growth.reason}</>}
        </p>
      </div>

      <div className="stats">
        {per && <Stat k="Value per share" v={usd(v.value_per_share!)} n={price != null ? `Price ${usd(price)}` : 'Add a price to compare'} />}
        <Stat k="Enterprise value" v={mm(v.enterprise_value)} n="Value of the whole business" />
        <Stat k="Equity value" v={mm(v.equity_value)} n={`After ${mm(v.net_debt)} net debt`} />
        <Stat k="After-forecast share" v={pct(termShare, 0)} n="Of enterprise value" />
        {v.implied_exit_multiple != null && <Stat k="Implied exit multiple" v={`${num(v.implied_exit_multiple, 1)}x`} n="What the growth-forever case implies" />}
        {v.implied_terminal_growth != null && <Stat k="Implied growth forever" v={pct(v.implied_terminal_growth)} n="What the exit multiple implies" />}
      </div>

      {r && (
        <section className="card">
          <h2>What the price is asking you to believe</h2>
          <p className="sub">Reverse DCF: keep everything else as you set it, then solve for the one input that makes the model equal the price. It is a question to investigate, not a verdict.</p>
          <div className="grid2">
            <Implied title="Yearly revenue growth" yours={pct(r.model_average_growth)} sol={r.implied_growth} f={(x) => pct(x)} />
            <Implied title="Discount rate" yours={pct(f.wacc, 2)} sol={r.implied_discount_rate} f={(x) => pct(x, 2)} />
          </div>
        </section>
      )}

      <div className="grid2">
        <section className="card">
          <h2>Which assumptions matter most</h2>
          <p className="sub">Each bar moves ONE assumption to a low and high setting and shows the {per ? 'value per share' : 'equity value'}.</p>
          <Tornado bars={d.tornado} base={d.sensitivity.base_output} fmt={fmt} />
        </section>
        <section className="card">
          <h2>{d.sensitivity.x_label} against {d.sensitivity.y_label.toLowerCase()}</h2>
          <p className="sub">{price != null ? `Teal cells are worth more than the ${usd(price)} price, coral less.` : 'Value in each combination. The outlined cell is your case.'}</p>
          <Grid d={d} price={price} per={per} />
        </section>
      </div>

      <section className="card">
        <h2>Forecast</h2>
        <p className="sub">Free cash flow = operating profit after tax + depreciation − capital spending − change in working capital. $ millions.</p>
        <div style={{ overflowX: 'auto' }}>
          <table className="t">
            <thead><tr><th>Year</th><th>Revenue</th><th>Operating profit</th><th>After-tax profit</th><th>Depreciation</th><th>Capital spending</th><th>Working capital change</th><th>Free cash flow</th><th>Present value</th></tr></thead>
            <tbody>
              {d.projection.map((p) => (
                <tr key={p.year}>
                  <td>{p.year}</td><td>{p.revenue.toFixed(0)}</td><td>{p.ebit.toFixed(0)}</td><td>{p.nopat.toFixed(0)}</td><td>{p.da.toFixed(0)}</td>
                  <td>{p.capex.toFixed(0)}</td><td>{p.delta_nwc.toFixed(0)}</td><td><b>{p.fcf.toFixed(0)}</b></td><td>{p.pv_fcf.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ValueBar explicit={v.pv_explicit} terminal={v.pv_terminal_value} />
      </section>

      <section className="card">
        <details className="assume">
          <summary>How this works, and what it leaves out</summary>
          <ul className="notes" style={{ marginTop: 12 }}>
            {(meta?.assumptions.dcf ?? []).map((a) => <li key={a}>{a}</li>)}
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

function Implied({ title, yours, sol, f }: { title: string; yours: string; sol: { available: boolean; value?: number | null; reason?: string | null; unique?: boolean | null }; f: (x: number) => string }) {
  return (
    <div>
      <h2 style={{ fontSize: 14 }}>{title}</h2>
      {sol.available && sol.value != null ? (
        <>
          <p style={{ font: '600 26px var(--sans)', marginTop: 4 }}>{f(sol.value)}</p>
          <p className="hint">The price implies this. You assumed {yours}.{sol.unique === false && ' More than one value fits, so this is the first found.'}</p>
        </>
      ) : <p className="hint" style={{ marginTop: 6 }}>No value in the search range matches the price. {sol.reason}</p>}
    </div>
  )
}

function Grid({ d, price, per }: { d: DCFResponse; price?: number; per: boolean }) {
  const g = d.sensitivity
  const base = g.base_output
  const isRate = g.y_label === 'Terminal growth'
  const cell = (c: number | null) => {
    if (c == null) return { background: 'transparent', color: 'var(--muted)' }
    const ref = price ?? base
    const rel = Math.max(-1, Math.min(1, (c - ref) / (ref || 1)))
    const col = rel >= 0 ? 'var(--teal)' : 'var(--coral)'
    return { background: `color-mix(in srgb, ${col} ${Math.round(Math.abs(rel) * 60)}%, var(--panel))`, color: 'var(--text)' }
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="t" style={{ tableLayout: 'fixed', minWidth: 380 }}>
        <thead>
          <tr><th style={{ width: 90, fontSize: 12 }}>{g.y_label} ↓ {g.x_label} →</th>{g.x_values.map((x) => <th key={x}>{pct(x, 1)}</th>)}</tr>
        </thead>
        <tbody>
          {g.grid.map((row, i) => (
            <tr key={i}>
              <td style={{ color: 'var(--muted)' }}>{isRate ? pct(g.y_values[i], 1) : `${g.y_values[i].toFixed(1)}x`}</td>
              {row.map((c, j) => {
                const isBase = i === 2 && j === 2
                return (
                  <td key={j} style={{ ...cell(c), textAlign: 'center', borderRadius: 4, outline: isBase ? '2px solid var(--accent)' : undefined, outlineOffset: -2 }}
                    title={c == null ? 'No finite value: growth is at or above the discount rate' : undefined}>
                    {c == null ? 'n/a' : per ? usd(c) : mm(c)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ValueBar({ explicit, terminal }: { explicit: number; terminal: number }) {
  const total = explicit + terminal
  const a = total > 0 ? (explicit / total) * 100 : 0
  return (
    <div style={{ marginTop: 16 }}>
      <p className="hint" style={{ marginBottom: 6 }}>Where the enterprise value comes from</p>
      <div style={{ display: 'flex', height: 14, borderRadius: 4, overflow: 'hidden', gap: 2 }} role="img"
        aria-label={`Forecast years ${a.toFixed(0)} percent, after the forecast ${(100 - a).toFixed(0)} percent`}>
        <div style={{ width: `${a}%`, background: 'var(--blue)' }} />
        <div style={{ width: `${100 - a}%`, background: 'var(--brass)' }} />
      </div>
      <div className="legend">
        <span><i style={{ borderColor: 'var(--blue)' }} />Forecast years: {mm(explicit)} ({a.toFixed(0)}%)</span>
        <span><i style={{ borderColor: 'var(--brass)' }} />After the forecast: {mm(terminal)} ({(100 - a).toFixed(0)}%)</span>
      </div>
    </div>
  )
}
