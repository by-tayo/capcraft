import { useId } from 'react'

type Num = { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; prefix?: string; hint?: string }

/** A number box. Typing is free-form; the value is clamped on blur. */
export function NumberField({ label, value, onChange, min, max, step = 1, prefix, hint }: Num) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-wrap">
        {prefix && <span className="prefix">{prefix}</span>}
        <input
          id={id} className="input" type="number" inputMode="decimal" value={Number.isFinite(value) ? value : ''}
          min={min} max={max} step={step} style={prefix ? undefined : { paddingLeft: 11 }}
          onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))}
          onBlur={() => {
            let v = Number.isFinite(value) ? value : (min ?? 0)
            if (min != null) v = Math.max(min, v)
            if (max != null) v = Math.min(max, v)
            if (v !== value) onChange(v)
          }}
        />
      </div>
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

type Sl = { label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; format: (v: number) => string; hint?: string }

export function SliderField({ label, value, onChange, min, max, step, format, hint }: Sl) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}<span className="value">{format(value)}</span></label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}
