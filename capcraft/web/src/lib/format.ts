const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1, style: 'currency', currency: 'USD' })
const whole = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0, style: 'currency', currency: 'USD' })

/** $1,234,567 */
export const money = (x: number) => whole.format(Math.round(x))
/** $1.2M, for axes and tight spaces */
export const moneyShort = (x: number) => compact.format(x)
/** 0.073 -> 7.3% */
export const pct = (x: number | null | undefined, d = 1) => (x == null ? 'n/a' : `${(x * 100).toFixed(d)}%`)
export const num = (x: number | null | undefined, d = 2) => (x == null ? 'n/a' : x.toFixed(d))
/** 0.734 -> "73 in 100" style odds, rounded sensibly */
export const outOfTen = (p: number) => {
  const n = Math.round(p * 10)
  return n === 0 && p > 0 ? 'fewer than 1 in 10' : n === 10 && p < 1 ? 'nearly every' : `${n} of 10`
}
