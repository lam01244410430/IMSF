/**
 * Formatting thuần — không platform, unit-test bằng Vitest (doc §8.2 quy tắc 4).
 * China-first (§2): tiền tệ mặc định CNY, timezone Asia/Shanghai, zh-CN.
 *
 * LƯU Ý QUAN TRỌNG (§5.3 + backend): `receipt_lines.price` là TỔNG TIỀN CỦA
 * DÒNG (tiểu kế), không phải đơn giá — backend đối soát bằng SUM(price).
 * UI sửa "đơn giá" thì phải nhân với số lượng rồi làm tròn 2dp mới ra price
 * gửi lên. Hàm `lineTotal` là chỗ duy nhất làm phép tính đó.
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

/** Thứ tự hiển thị chuẩn trong mọi selector tiền tệ (P2-06, D-F7 đã giải quyết). */
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

/** Ký hiệu tiền tệ — NGUỒN DUY NHẤT, mọi selector/format đều dùng map này. */
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

/**
 * Chuẩn hoá một mã tiền tệ dạng string tự do (API / household default) về
 * Currency: mã lạ / null / undefined → 'CNY' (China-first). Backend P2-06
 * chấp nhận cả 14 mã nên USD/EUR/... không còn bị ép về CNY nữa.
 */
export function resolveCurrency(value: string | null | undefined): Currency {
  return (SUPPORTED_CURRENCIES as readonly string[]).includes(value ?? '')
    ? (value as Currency)
    : 'CNY'
}

/** ¥280.00 — grouping thủ công (không dựa vào Intl, Mini Program nào cũng chạy). */
export function formatMoney(amount: number | null | undefined, currency: Currency = 'CNY'): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const symbol = CURRENCY_SYMBOL[currency] ?? '¥'
  const sign = amount < 0 ? '-' : ''
  const [int, frac] = Math.abs(amount).toFixed(2).split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${sign}${symbol}${grouped}.${frac}`
}

/** Làm tròn 2 chữ số thập phân (tránh lỗi float 0.1 + 0.2). */
export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

/**
 * Tiểu kế của một dòng = số lượng × đơn giá, làm tròn 2dp.
 * Đây chính là `price` trong payload confirm (§5.3) và là số backend cộng
 * vào SUM(price) khi đối soát 2%.
 */
export function lineTotal(quantity: number, unitPrice: number): number {
  return round2(quantity * unitPrice)
}

/** Đơn giá suy ra từ dòng đã lưu: price (tiểu kế) / quantity. */
export function unitPriceFromLine(lineTotalAmount: number, quantity: number): number {
  if (!quantity || quantity <= 0) return round2(lineTotalAmount)
  return round2(lineTotalAmount / quantity)
}

/** Lệch đối soát: { diff, pct } — pct 1 chữ số thập phân (§5.3). */
export function reconciliationDiff(
  totalAmount: number,
  linesSum: number,
): { diff: number; pct: number; withinThreshold: boolean } {
  const diff = round2(Math.abs(totalAmount - linesSum))
  const pct = totalAmount > 0 ? Math.round((diff / totalAmount) * 1000) / 10 : 0
  return { diff, pct, withinThreshold: totalAmount > 0 ? diff / totalAmount <= 0.02 : false }
}

function partsInTimeZone(date: Date, timeZone: string): { y: number; m: number; d: number; hh: number; mm: number } | null {
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

/** Ngày tương đối: 今天 09:12 / 昨天 18:40 / 11月18日 (§5.1). */
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

/** Thời gian đã trôi dạng m:ss — "0:42", cập nhật mỗi giây (§5.2). */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

/** Ký tự đầu làm glyph cửa hàng trong vòng accentContainer (§5.1). */
export function storeGlyph(storeName: string | null | undefined): string {
  const name = (storeName ?? '').trim()
  if (!name) return '?'
  return name[0]
}

/** Bỏ các số 0 thừa sau dấu thập phân: "100.00" → "100", "100.50" → "100.5". */
function stripTrailingZeros(fixed: string): string {
  if (!fixed.includes('.')) return fixed
  return fixed.replace(/0+$/, '').replace(/\.$/, '')
}

/**
 * Số tiền hiển thị cho sổ chi tiêu (FE-03, quy tắc của Lam 2026-11-21):
 * grouping + ký hiệu tiền tệ như formatMoney, nhưng BỎ các số 0 thừa sau
 * dấu thập phân: 100.00 → ¥100, 100.50 → ¥100.5, 100.25 → ¥100.25,
 * 0.50 → ¥0.5, 0 → ¥0, 0.10 → ¥0.1.
 * Backend lưu NUMERIC(10,2); chỉ cách HIỂN THỊ bỏ số 0 thừa.
 * formatMoney KHÔNG đổi — các màn receipt vẫn dùng 2dp cố định.
 */
export function formatAmount(amount: number | null | undefined, currency: Currency = 'CNY'): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const symbol = CURRENCY_SYMBOL[currency] ?? '¥'
  const sign = amount < 0 ? '-' : ''
  const [int, frac] = Math.abs(amount).toFixed(2).split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const fracTrimmed = frac.replace(/0+$/, '')
  return fracTrimmed ? `${sign}${symbol}${grouped}.${fracTrimmed}` : `${sign}${symbol}${grouped}`
}

/**
 * Chuẩn hoá ô nhập số tiền khi blur/submit (FE-03): "100.50" → "100.5",
 * "100.00" → "100". Chỉ chuẩn hoá khi phần thập phân ≤ 2 chữ số — nhập
 * quá 2 chữ số thập phân thì giữ nguyên để validation báo lỗi
 * 「金额最多保留两位小数」, không lặng lẽ làm tròn.
 * Không parse được thì giữ nguyên để validation báo 「请输入正确的金额」.
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

/** Offset của một timezone dạng "+08:00" (Intl longOffset), fallback UTC. */
function tzOffsetString(timeZone: string, at: Date): string {
  try {
    const part = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'longOffset' })
      .formatToParts(at)
      .find((p) => p.type === 'timeZoneName')?.value
    const m = /^GMT([+-])(\d{2}):(\d{2})$/.exec(part ?? '')
    if (m) return `${m[1]}${m[2]}:${m[3]}`
  } catch {
    // rơi xuống fallback UTC bên dưới
  }
  return 'Z'
}

/** 00:00 ngày (y-m-d) theo timezone của nhà, dạng ISO có offset (vd +08:00). */
function zonedDayStartIso(y: number, m: number, d: number, timeZone: string): string {
  const at = new Date(Date.UTC(y, m - 1, d))
  const off = tzOffsetString(timeZone, at)
  if (off === 'Z') return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T00:00:00Z`
  return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T00:00:00${off}`
}

/** Tháng hiện tại dạng "YYYY-MM" theo timezone của nhà (mặc định Asia/Shanghai). */
export function currentMonth(timeZone = 'Asia/Shanghai'): string {
  const p = partsInTimeZone(new Date(), timeZone)
  if (!p) {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  }
  return `${p.y}-${String(p.m).padStart(2, '0')}`
}

/** Ngày hôm nay dạng "YYYY-MM-DD" theo timezone của nhà (mặc định cho ô ngày). */
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

/** Dịch tháng: shiftMonth("2026-11", -1) → "2026-10", qua năm vẫn đúng. */
export function shiftMonth(month: string, delta: number): string {
  const m = /^(\d{4})-(\d{2})$/.exec(month)
  if (!m) return month
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1 + delta, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}

/**
 * Khoảng [from, to) của một tháng — dùng cho GET /spending/summary?from=&to=
 * (backend: occurred_at >= from, < to; ISO 8601, naive = UTC).
 * Ranh giới là 00:00 theo timezone của nhà (vd Asia/Shanghai +08:00),
 * không phải 00:00 UTC — để chi ngày 1 đầu tháng theo giờ nhà không rơi
 * sang tháng trước.
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

/** Khoảng [from, to) của cả một năm (cho danh sách by_month trong năm). */
export function yearRange(year: number, timeZone = 'Asia/Shanghai'): { from: string; to: string } {
  return {
    from: zonedDayStartIso(year, 1, 1, timeZone),
    to: zonedDayStartIso(year + 1, 1, 1, timeZone),
  }
}

/**
 * Ngày "YYYY-MM-DD" (ô date picker) → occurred_at ISO gửi lên API:
 * 00:00 ngày đó theo timezone của nhà. Backend lưu TIMESTAMPTZ.
 */
export function dateToOccurredAt(date: string, timeZone = 'Asia/Shanghai'): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!m) return ''
  return zonedDayStartIso(Number(m[1]), Number(m[2]), Number(m[3]), timeZone)
}

/** occurred_at ISO → "YYYY-MM-DD" theo timezone của nhà (điền lại ô date khi sửa). */
export function occurredAtToDate(iso: string | null | undefined, timeZone = 'Asia/Shanghai'): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const p = partsInTimeZone(date, timeZone)
  if (!p) return ''
  return `${p.y}-${String(p.m).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`
}

/** rgba(hex, alpha) — dùng cho border/background cần opacity mà không thêm token mới (§5.1 capture card). */
export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const n = Number.parseInt(full, 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r},${g},${b},${alpha})`
}
