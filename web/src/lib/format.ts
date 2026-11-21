/**
 * Formatting helpers — port of `frontend/src/utils/format.ts` (Taro) to
 * plain web. No Taro imports; identical rules:
 * - 14 currencies, no conversion, no cross-currency sums.
 * - `formatAmount` strips redundant trailing zeros (100.00 → ¥100,
 *   100.50 → ¥100.5); `formatMoney` keeps fixed 2dp (receipt screens).
 * - China-first: default currency CNY, timezone Asia/Shanghai.
 */

export type Currency =
  | 'CNY'
  | 'VND'
  | 'USD'
  | 'EUR'
  | 'HKD'
  | 'THB'
  | 'MYR'
  | 'SGD'
  | 'IDR'
  | 'PHP'
  | 'KHR'
  | 'LAK'
  | 'MMK'
  | 'BND'

/** Display order in every currency selector (P2-06, D-F7). */
export const SUPPORTED_CURRENCIES: readonly Currency[] = [
  'CNY',
  'VND',
  'USD',
  'EUR',
  'HKD',
  'THB',
  'MYR',
  'SGD',
  'IDR',
  'PHP',
  'KHR',
  'LAK',
  'MMK',
  'BND',
]

/** Currency symbols — the single source; every selector/format uses it. */
export const CURRENCY_SYMBOL: Record<Currency, string> = {
  CNY: '¥',
  VND: '₫',
  USD: '$',
  EUR: '€',
  HKD: 'HK$',
  THB: '฿',
  MYR: 'RM',
  SGD: 'S$',
  IDR: 'Rp',
  PHP: '₱',
  KHR: '៛',
  LAK: '₭',
  MMK: 'K',
  BND: 'B$',
}

/** zh-CN labels for the 14 currencies in selectors. */
export const CURRENCY_LABELS: Record<Currency, string> = {
  CNY: '人民币',
  VND: '越南盾',
  USD: '美元',
  EUR: '欧元',
  HKD: '港元',
  THB: '泰铢',
  MYR: '马来西亚林吉特',
  SGD: '新加坡元',
  IDR: '印度尼西亚盾',
  PHP: '菲律宾比索',
  KHR: '柬埔寨瑞尔',
  LAK: '老挝基普',
  MMK: '缅甸元',
  BND: '文莱元',
}

/**
 * Normalise a free-form currency code (API / household default) to a
 * Currency: unknown / null / undefined → 'CNY' (China-first).
 */
export function resolveCurrency(value: string | null | undefined): Currency {
  return (SUPPORTED_CURRENCIES as readonly string[]).includes(value ?? '')
    ? (value as Currency)
    : 'CNY'
}

/** ¥280.00 — manual grouping, fixed 2dp (receipt screens). */
export function formatMoney(
  amount: number | null | undefined,
  currency: Currency = 'CNY',
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const symbol = CURRENCY_SYMBOL[currency] ?? '¥'
  const sign = amount < 0 ? '-' : ''
  const [int, frac] = Math.abs(amount).toFixed(2).split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${sign}${symbol}${grouped}.${frac}`
}

/** Round to 2 decimal places (avoids 0.1 + 0.2 float error). */
export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

/** Line subtotal = quantity × unit price, rounded to 2dp. This is the
 *  `price` in the confirm payload and in SUM(price) reconciliation. */
export function lineTotal(quantity: number, unitPrice: number): number {
  return round2(quantity * unitPrice)
}

/** Unit price implied by a stored line: price (subtotal) / quantity. */
export function unitPriceFromLine(lineTotalAmount: number, quantity: number): number {
  if (!quantity || quantity <= 0) return round2(lineTotalAmount)
  return round2(lineTotalAmount / quantity)
}

/** Reconciliation gap: { diff, pct } — pct to 1 decimal place. */
export function reconciliationDiff(
  totalAmount: number,
  linesSum: number,
): { diff: number; pct: number; withinThreshold: boolean } {
  const diff = round2(Math.abs(totalAmount - linesSum))
  const pct = totalAmount > 0 ? Math.round((diff / totalAmount) * 1000) / 10 : 0
  return {
    diff,
    pct,
    withinThreshold: totalAmount > 0 ? diff / totalAmount <= 0.02 : false,
  }
}

function partsInTimeZone(
  date: Date,
  timeZone: string,
): { y: number; m: number; d: number; hh: number; mm: number } | null {
  try {
    const fmt = new Intl.DateTimeFormat('zh-CN', {
      timeZone,
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
    })
    const parts = fmt.formatToParts(date)
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0)
    return { y: get('year'), m: get('month'), d: get('day'), hh: get('hour'), mm: get('minute') }
  } catch {
    return null
  }
}

/** Relative date: 今天 09:12 / 昨天 18:40 / 11月18日. */
export function formatRelativeDate(iso: string | null | undefined, timeZone = 'Asia/Shanghai'): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const p = partsInTimeZone(date, timeZone)
  const now = partsInTimeZone(new Date(), timeZone)
  const hh = String(p?.hh ?? date.getHours()).padStart(2, '0')
  const mm = String(p?.mm ?? date.getMinutes()).padStart(2, '0')
  if (p && now) {
    const dayStart = (x: { y: number; m: number; d: number }) => Date.UTC(x.y, x.m - 1, x.d)
    const diffDays = Math.round((dayStart(now) - dayStart(p)) / 86400000)
    if (diffDays === 0) return `今天 ${hh}:${mm}`
    if (diffDays === 1) return `昨天 ${hh}:${mm}`
    return `${p.m}月${p.d}日`
  }
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

/** Strip redundant trailing zeros: "100.00" → "100", "100.50" → "100.5". */
function stripTrailingZeros(fixed: string): string {
  if (!fixed.includes('.')) return fixed
  return fixed.replace(/0+$/, '').replace(/\.$/, '')
}

/**
 * Display amount for the expense book (FE-03, Lam's rule): grouping +
 * currency symbol like formatMoney, but trailing zeros after the decimal
 * point are stripped: 100.00 → ¥100, 100.50 → ¥100.5, 100.25 → ¥100.25,
 * 0.50 → ¥0.5, 0 → ¥0, 0.10 → ¥0.1.
 * The backend stores NUMERIC(10,2); only the DISPLAY strips zeros.
 */
export function formatAmount(
  amount: number | null | undefined,
  currency: Currency = 'CNY',
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const symbol = CURRENCY_SYMBOL[currency] ?? '¥'
  const sign = amount < 0 ? '-' : ''
  const [int, frac] = Math.abs(amount).toFixed(2).split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const fracTrimmed = frac.replace(/0+$/, '')
  return fracTrimmed
    ? `${sign}${symbol}${grouped}.${fracTrimmed}`
    : `${sign}${symbol}${grouped}`
}

/**
 * Normalise an amount input on submit: "100.50" → "100.5", "100.00" →
 * "100". Only normalises when the fraction is ≤ 2 digits — more than 2
 * stays untouched so validation can report 「金额最多保留两位小数」.
 * Unparseable input is returned unchanged so validation reports
 * 「请输入正确的金额」.
 */
export function normalizeAmountInput(text: string): string {
  const t = text.trim().replace(/,/g, '')
  if (t === '') return ''
  const m = /^(-?\d+)(?:\.(\d+))?$/.exec(t)
  if (!m) return text
  if ((m[2] ?? '').length > 2) return text
  const n = Number(t)
  if (Number.isNaN(n)) return text
  return stripTrailingZeros(n.toFixed(2))
}

/**
 * Client-side validation of the amount field (server is authoritative —
 * amount Decimal gt=0, NUMERIC(10,2)). Returns a zh-CN message or null.
 */
export function validateAmountText(text: string): string | null {
  const t = text.trim()
  if (t === '') return '请输入金额'
  if (!/^-?\d+(\.\d+)?$/.test(t)) return '请输入正确的金额'
  if (!/^-?\d+(\.\d{1,2})?$/.test(t)) return '金额最多保留两位小数'
  if (Number(t) <= 0) return '金额必须大于 0'
  return null
}

/** Offset of a timezone as "+08:00" (Intl longOffset), fallback UTC. */
function tzOffsetString(timeZone: string, at: Date): string {
  try {
    const part = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'longOffset' })
      .formatToParts(at)
      .find((p) => p.type === 'timeZoneName')?.value
    const m = /^GMT([+-])(\d{2}):(\d{2})$/.exec(part ?? '')
    if (m) return `${m[1]}${m[2]}:${m[3]}`
  } catch {
    // falls through to the UTC fallback below
  }
  return 'Z'
}

/** 00:00 of day (y-m-d) in the household timezone, as ISO with offset. */
function zonedDayStartIso(y: number, m: number, d: number, timeZone: string): string {
  const at = new Date(Date.UTC(y, m - 1, d))
  const off = tzOffsetString(timeZone, at)
  if (off === 'Z')
    return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T00:00:00Z`
  return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T00:00:00${off}`
}

/** Current month as "YYYY-MM" in the household timezone. */
export function currentMonth(timeZone = 'Asia/Shanghai'): string {
  const p = partsInTimeZone(new Date(), timeZone)
  if (!p) {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  }
  return `${p.y}-${String(p.m).padStart(2, '0')}`
}

/** Today as "YYYY-MM-DD" in the household timezone (form date default). */
export function todayDate(timeZone = 'Asia/Shanghai'): string {
  const p = partsInTimeZone(new Date(), timeZone)
  if (!p) {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }
  return `${p.y}-${String(p.m).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`
}

/** "2026-11" → "2026年11月". */
export function monthLabel(month: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(month)
  if (!m) return month
  return `${m[1]}年${Number(m[2])}月`
}

/** Shift a month: shiftMonth("2026-11", -1) → "2026-10", across years. */
export function shiftMonth(month: string, delta: number): string {
  const m = /^(\d{4})-(\d{2})$/.exec(month)
  if (!m) return month
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1 + delta, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}

/**
 * [from, to) range of a month — for GET /spending/summary?from=&to=
 * (backend: occurred_at >= from, < to; ISO 8601, naive = UTC).
 * Boundaries are 00:00 in the household timezone, not 00:00 UTC.
 */
export function monthRange(month: string, timeZone = 'Asia/Shanghai'): { from: string; to: string } {
  const m = /^(\d{4})-(\d{2})$/.exec(month)
  if (!m) return { from: '', to: '' }
  const y = Number(m[1])
  const mo = Number(m[2])
  const next = mo === 12 ? { y: y + 1, m: 1 } : { y, m: mo + 1 }
  return {
    from: zonedDayStartIso(y, mo, 1, timeZone),
    to: zonedDayStartIso(next.y, next.m, 1, timeZone),
  }
}

/** [from, to) range of a whole year (for the by_month list of a year). */
export function yearRange(year: number, timeZone = 'Asia/Shanghai'): { from: string; to: string } {
  return {
    from: zonedDayStartIso(year, 1, 1, timeZone),
    to: zonedDayStartIso(year + 1, 1, 1, timeZone),
  }
}

/**
 * A "YYYY-MM-DD" date-picker value → occurred_at ISO to send to the API:
 * 00:00 of that day in the household timezone. Backend stores TIMESTAMPTZ.
 */
export function dateToOccurredAt(date: string, timeZone = 'Asia/Shanghai'): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!m) return ''
  return zonedDayStartIso(Number(m[1]), Number(m[2]), Number(m[3]), timeZone)
}

/** occurred_at ISO → "YYYY-MM-DD" in the household timezone (edit form). */
export function occurredAtToDate(iso: string | null | undefined, timeZone = 'Asia/Shanghai'): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const p = partsInTimeZone(date, timeZone)
  if (!p) return ''
  return `${p.y}-${String(p.m).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`
}
