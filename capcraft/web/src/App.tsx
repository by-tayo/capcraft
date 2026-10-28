import { useEffect, useState } from 'react'
import { api, type Meta } from './api/client'
import { PlanTab } from './tabs/PlanTab'
import { DcfTab } from './tabs/DcfTab'
import { XrayTab } from './tabs/XrayTab'

const TABS = [
  { id: 'plan', label: 'Plan vs. reality' },
  { id: 'xray', label: 'Portfolio X-ray' },
  { id: 'dcf', label: 'Valuation' },
] as const
type TabId = (typeof TABS)[number]['id']

function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <path d="M5 25 L12 16 L18 20 L27 7" fill="none" stroke="#E3B04B" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 25 L12 21 L18 24 L27 18" fill="none" stroke="#5F82E8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity=".85" />
    </svg>
  )
}

export default function App() {
  const [tab, setTab] = useState<TabId>('plan')
  const [meta, setMeta] = useState<Meta | null>(null)
  useEffect(() => { api.meta().then(setMeta).catch(() => setMeta(null)) }, [])

  return (
    <div className="shell">
      <header className="top">
        <div className="brand"><Logo />CapCraft</div>
        <nav className="tabs" role="tablist" aria-label="Tools">
          {TABS.map((t) => (
            <button key={t.id} role="tab" className="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
        <p className="disclaimer">{meta?.disclaimer ?? 'For learning only. Not financial advice.'}</p>
      </header>
      {tab === 'plan' && <PlanTab meta={meta} />}
      {tab === 'xray' && <XrayTab meta={meta} />}
      {tab === 'dcf' && <DcfTab meta={meta} />}
    </div>
  )
}
