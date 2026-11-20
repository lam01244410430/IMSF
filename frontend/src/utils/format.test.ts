import { describe, expect, it } from 'vitest'
import {
  formatElapsed,
  formatMoney,
  formatRelativeDate,
  lineTotal,
  reconciliationDiff,
  round2,
  storeGlyph,
  unitPriceFromLine,
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
