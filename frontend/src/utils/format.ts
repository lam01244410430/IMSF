/**
 * Formatting thuần — không platform, unit-test bằng Vitest (doc §8.2 quy tắc 4).
 * China-first (§2): tiền tệ mặc định CNY, timezone Asia/Shanghai, zh-CN.
 *
 * LƯU Ý QUAN TRỌNG (§5.3 + backend): `receipt_lines.price` là TỔNG TIỀN CỦA
 * DÒNG (tiểu kế), không phải đơn giá — backend đối soát bằng SUM(price).
 * UI sửa "đơn giá" thì phải nhân với số lượng rồi làm tròn 2dp mới ra price
 * gửi lên. Hàm `lineTotal` là chỗ duy nhất làm phép tính đó.
 */

export type Currency = 'CNY' | 'VND'

const CURRENCY_SYMBOL: Record<Currency, string> = { CNY: '¥', VND: '₫' }

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

/** Ký tự đầu làm glyph cửa hàng trong vòng primaryContainer (§5.1). */
export function storeGlyph(storeName: string | null | undefined): string {
  const name = (storeName ?? '').trim()
  if (!name) return '?'
  return name[0]
}
