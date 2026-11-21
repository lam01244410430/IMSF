import { describe, expect, it } from 'vitest'
import {
  currentMonth,
  dateToOccurredAt,
  formatAmount,
  formatElapsed,
  formatMoney,
  formatRelativeDate,
  lineTotal,
  monthLabel,
  monthRange,
  normalizeAmountInput,
  occurredAtToDate,
  reconciliationDiff,
  round2,
  shiftMonth,
  storeGlyph,
  todayDate,
  unitPriceFromLine,
  withAlpha,
  yearRange,
} from './format'

describe('formatMoney', () => {
  it('CNY mặc định, 2dp + grouping', () => {
    expect(formatMoney(280)).toBe('¥280.00')
    expect(formatMoney(1234.5)).toBe('¥1,234.50')
    expect(formatMoney(-3.6)).toBe('-¥3.60')
    expect(formatMoney(0)).toBe('¥0.00')
  })
  it('VND dùng ₫; null → —', () => {
    expect(formatMoney(50000, 'VND')).toBe('₫50,000.00')
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney(undefined)).toBe('—')
  })
})

describe('lineTotal / unitPriceFromLine — price là tiểu kế (§5.3)', () => {
  it('qty × đơn giá, làm tròn 2dp', () => {
    expect(lineTotal(2, 2)).toBe(4)
    expect(lineTotal(3, 1.115)).toBe(3.35)
    expect(lineTotal(0.5, 10)).toBe(5)
    expect(round2(0.1 + 0.2)).toBe(0.3)
  })
  it('đơn giá suy ra từ tiểu kế đã lưu', () => {
    expect(unitPriceFromLine(4, 2)).toBe(2)
    expect(unitPriceFromLine(3.6, 3)).toBe(1.2)
    expect(unitPriceFromLine(5, 0)).toBe(5)
  })
})

describe('reconciliationDiff — 2% (§5.3)', () => {
  it('diff + pct 1 chữ số thập phân', () => {
    const r = reconciliationDiff(132, 128.4)
    expect(r.diff).toBe(3.6)
    expect(r.pct).toBe(2.7)
    expect(r.withinThreshold).toBe(false)
    expect(reconciliationDiff(100, 98).withinThreshold).toBe(true) // đúng 2.00% pass
    expect(reconciliationDiff(100, 100).pct).toBe(0)
  })
})

describe('formatElapsed', () => {
  it('m:ss', () => {
    expect(formatElapsed(0)).toBe('0:00')
    expect(formatElapsed(42)).toBe('0:42')
    expect(formatElapsed(125)).toBe('2:05')
  })
})

describe('formatRelativeDate', () => {
  it('今天 / 昨天 / M月d日 theo Asia/Shanghai', () => {
    const now = new Date()
    const todayIso = now.toISOString()
    expect(formatRelativeDate(todayIso)).toMatch(/^今天 \d{2}:\d{2}$/)
    const yesterday = new Date(now.getTime() - 24 * 3600 * 1000).toISOString()
    expect(formatRelativeDate(yesterday)).toMatch(/^昨天 \d{2}:\d{2}$/)
    expect(formatRelativeDate('2026-11-18T10:00:00+08:00')).toBe('11月18日')
    expect(formatRelativeDate(null)).toBe('')
  })
})

describe('storeGlyph', () => {
  it('ký tự đầu / fallback ?', () => {
    expect(storeGlyph('永辉超市')).toBe('永')
    expect(storeGlyph('')).toBe('?')
    expect(storeGlyph(null)).toBe('?')
  })
})

describe('withAlpha', () => {
  it('hex 6 ký tự → rgba', () => {
    expect(withAlpha('#2E7D32', 0.6)).toBe('rgba(46,125,50,0.6)')
    expect(withAlpha('#C8E6C9', 0.4)).toBe('rgba(200,230,201,0.4)')
  })
  it('hex 3 ký tự → rgba', () => {
    expect(withAlpha('#fff', 0.5)).toBe('rgba(255,255,255,0.5)')
  })
})

describe('formatAmount — sổ chi tiêu: bỏ số 0 thừa sau thập phân (FE-03, quy tắc Lam)', () => {
  it('các trường hợp trong spec: 100.00→100, 100.50→100.5, 100.25→100.25, 0.50→0.5, 0→0, 0.10→0.1', () => {
    expect(formatAmount(100)).toBe('¥100')
    expect(formatAmount(100.5)).toBe('¥100.5')
    expect(formatAmount(100.25)).toBe('¥100.25')
    expect(formatAmount(0.5)).toBe('¥0.5')
    expect(formatAmount(0)).toBe('¥0')
    expect(formatAmount(0.1)).toBe('¥0.1')
  })
  it('grouping + ký hiệu tiền tệ giữ nguyên (¥ CNY, ₫ VND)', () => {
    expect(formatAmount(1234.5)).toBe('¥1,234.5')
    expect(formatAmount(50000, 'VND')).toBe('₫50,000')
    expect(formatAmount(1234567.89)).toBe('¥1,234,567.89')
    expect(formatAmount(1234567.8, 'VND')).toBe('₫1,234,567.8')
  })
  it('null / undefined / NaN → — (giống formatMoney)', () => {
    expect(formatAmount(null)).toBe('—')
    expect(formatAmount(undefined)).toBe('—')
    expect(formatAmount(Number.NaN)).toBe('—')
  })
  it('số âm chỉ là trường hợp phòng thủ của hàm thuần — API từ chối amount âm (gt=0) nên số âm không bao giờ đến từ API', () => {
    expect(formatAmount(-3.6)).toBe('-¥3.6')
    expect(formatAmount(-100)).toBe('-¥100')
  })
  it('formatMoney KHÔNG đổi — màn receipt vẫn 2dp cố định', () => {
    expect(formatMoney(100)).toBe('¥100.00')
    expect(formatMoney(100.5)).toBe('¥100.50')
  })
})

describe('normalizeAmountInput — chuẩn hoá ô nhập khi blur/submit (FE-03)', () => {
  it('bỏ số 0 thừa, bỏ dấu phẩy grouping', () => {
    expect(normalizeAmountInput('100.50')).toBe('100.5')
    expect(normalizeAmountInput('100.00')).toBe('100')
    expect(normalizeAmountInput('1,234.50')).toBe('1234.5')
    expect(normalizeAmountInput('0.10')).toBe('0.1')
    expect(normalizeAmountInput('')).toBe('')
  })
  it('quá 2 chữ số thập phân thì giữ nguyên — validation báo lỗi, không lặng lẽ làm tròn', () => {
    expect(normalizeAmountInput('100.005')).toBe('100.005')
    expect(normalizeAmountInput('1.234')).toBe('1.234')
  })
  it('không parse được thì giữ nguyên để validation báo lỗi', () => {
    expect(normalizeAmountInput('abc')).toBe('abc')
    expect(normalizeAmountInput('12a')).toBe('12a')
  })
})

describe('month helpers — sổ chi tiêu (FE-03)', () => {
  it('monthLabel: 2026-11 → 2026年11月', () => {
    expect(monthLabel('2026-11')).toBe('2026年11月')
    expect(monthLabel('2026-01')).toBe('2026年1月')
    expect(monthLabel('không-phải-tháng')).toBe('không-phải-tháng')
  })
  it('shiftMonth qua tháng và qua năm', () => {
    expect(shiftMonth('2026-11', -1)).toBe('2026-10')
    expect(shiftMonth('2026-11', 1)).toBe('2026-12')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(shiftMonth('2026-11', 0)).toBe('2026-11')
  })
  it('monthRange: [đầu tháng, đầu tháng sau) theo Asia/Shanghai (+08:00)', () => {
    expect(monthRange('2026-11')).toEqual({
      from: '2026-11-01T00:00:00+08:00',
      to: '2026-12-01T00:00:00+08:00',
    })
    expect(monthRange('2026-12')).toEqual({
      from: '2026-12-01T00:00:00+08:00',
      to: '2027-01-01T00:00:00+08:00',
    })
  })
  it('yearRange: [1/1, 1/1 năm sau)', () => {
    expect(yearRange(2026)).toEqual({
      from: '2026-01-01T00:00:00+08:00',
      to: '2027-01-01T00:00:00+08:00',
    })
  })
  it('dateToOccurredAt / occurredAtToDate đi và về đúng ngày theo Asia/Shanghai', () => {
    expect(dateToOccurredAt('2026-11-21')).toBe('2026-11-21T00:00:00+08:00')
    expect(occurredAtToDate('2026-11-21T00:00:00+08:00')).toBe('2026-11-21')
    expect(occurredAtToDate('2026-11-20T16:00:00Z')).toBe('2026-11-21') // 16:00 UTC = 00:00+08 hôm sau
    expect(dateToOccurredAt('không-phải-ngày')).toBe('')
    expect(occurredAtToDate(null)).toBe('')
  })
  it('currentMonth / todayDate đúng định dạng YYYY-MM / YYYY-MM-DD', () => {
    expect(currentMonth()).toMatch(/^\d{4}-\d{2}$/)
    expect(todayDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    // Hai hàm dùng cùng một timezone nên tháng của todayDate khớp currentMonth
    expect(todayDate().slice(0, 7)).toBe(currentMonth())
  })
})
