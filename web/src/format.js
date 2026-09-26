export const pct = (v, d = 0) => (v == null ? '–' : `${(v * 100).toFixed(d)}%`)
export const int = (v) => (v == null ? '–' : Math.round(v).toLocaleString('en-GB'))
export const num = (v, d = 1) => (v == null ? '–' : Number(v).toFixed(d))
export const gbp = (v) => {
  if (v == null) return '–'
  const a = Math.abs(v)
  if (a >= 1e6) return `£${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`
  if (a >= 1e4) return `£${Math.round(v / 1e3)}k`
  return `£${Math.round(v).toLocaleString('en-GB')}`
}
export const compact = (v) => {
  if (v == null) return '–'
  const a = Math.abs(v)
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (a >= 1e4) return `${(v / 1e3).toFixed(0)}k`
  return Math.round(v).toLocaleString('en-GB')
}
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const monthLabel = (m) => {
  if (!m) return ''
  const [y, mo] = m.split('-')
  return `${MONTHS[+mo - 1]} ${y.slice(2)}`
}
export const fmt = (v, kind) =>
  kind === 'pct' ? pct(v) : kind === 'days' ? num(v) : kind === 'score' ? num(v, 2) : int(v)
