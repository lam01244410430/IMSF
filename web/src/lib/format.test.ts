import { describe, expect, it } from 'vitest'
import {
  dateToOccurredAt,
  formatAmount,
  formatDateTime,
  formatMoney,
  monthLabel,
  monthRange,
  normalizeAmountInput,
  occurredAtToDate,
  resolveCurrency,
  shiftMonth,
  todayDate,
  validateAmountText,
} from './format'

describe('formatAmount — trailing zeros stripped (Lam rule)', () => {
  it.each([
    [100, 'CNY', '¥100'],
    [100.5, 'CNY', '¥100.5'],
    [100.25, 'CNY', '¥100.25'],
    [0.5, 'CNY', '¥0.5'],
    [0, 'CNY', '¥0'],
    [0.1, 'CNY', '¥0.1'],
    [1234.56, 'CNY', '¥1,234.56'],
    [100, 'VND', '₫100'],
    [100.5, 'USD', '$100.5'],
    [2500, 'EUR', '€2,500'],
  ])('formatAmount(%s, %s) = %s', (amount, currency, expected) => {
    expect(formatAmount(amount, currency as 'CNY')).toBe(expected)
  })

  it('null / undefined / NaN → —', () => {
    expect(formatAmount(null)).toBe('—')
    expect(formatAmount(undefined)).toBe('—')
    expect(formatAmount(Number.NaN)).toBe('—')
  })

  it('formatMoney keeps fixed 2dp (receipt screens unchanged)', () => {
    expect(formatMoney(100, 'CNY')).toBe('¥100.00')
    expect(formatMoney(100.5, 'CNY')).toBe('¥100.50')
  })
})

describe('resolveCurrency', () => {
  it('known codes pass through, unknown → CNY', () => {
    expect(resolveCurrency('VND')).toBe('VND')
    expect(resolveCurrency('USD')).toBe('USD')
    expect(resolveCurrency('XXX')).toBe('CNY')
    expect(resolveCurrency(null)).toBe('CNY')
    expect(resolveCurrency(undefined)).toBe('CNY')
  })
})

describe('validateAmountText', () => {
  it.each([
    ['', '请输入金额'],
    ['abc', '请输入正确的金额'],
    ['100.555', '金额最多保留两位小数'],
    ['0', '金额必须大于 0'],
    ['-5', '金额必须大于 0'],
    ['100', null],
    ['100.50', null],
    ['0.01', null],
  ])('%s → %s', (text, expected) => {
    expect(validateAmountText(text)).toBe(expected)
  })
})

describe('normalizeAmountInput', () => {
  it.each([
    ['100.50', '100.5'],
    ['100.00', '100'],
    ['100', '100'],
    ['100.555', '100.555'],
    ['abc', 'abc'],
    ['', ''],
  ])('%s → %s', (text, expected) => {
    expect(normalizeAmountInput(text)).toBe(expected)
  })
})

describe('month / date helpers', () => {
  it('monthLabel', () => {
    expect(monthLabel('2026-11')).toBe('2026年11月')
    expect(monthLabel('2026-01')).toBe('2026年1月')
  })

  it('shiftMonth across year boundaries', () => {
    expect(shiftMonth('2026-11', -1)).toBe('2026-10')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
  })

  it('monthRange is [first of month, first of next month) in household tz', () => {
    const { from, to } = monthRange('2026-11', 'Asia/Shanghai')
    expect(from).toBe('2026-11-01T00:00:00+08:00')
    expect(to).toBe('2026-12-01T00:00:00+08:00')
  })

  it('dateToOccurredAt / occurredAtToDate round-trip in household tz', () => {
    expect(dateToOccurredAt('2026-11-21', 'Asia/Shanghai')).toBe('2026-11-21T00:00:00+08:00')
    expect(occurredAtToDate('2026-11-21T00:00:00+08:00', 'Asia/Shanghai')).toBe('2026-11-21')
  })

  it('todayDate returns YYYY-MM-DD', () => {
    expect(todayDate('Asia/Shanghai')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('formatDateTime — admin absolute timestamps', () => {
  it('renders an ISO timestamp in Asia/Shanghai', () => {
    const out = formatDateTime('2026-11-22T00:00:00Z', 'zh-CN')
    // 2026-11-22 00:00 UTC = 08:00 in Asia/Shanghai.
    expect(out).toContain('2026')
    expect(out).toContain('8:00')
  })

  it('null / garbage → em dash / passthrough, never a crash', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
    expect(formatDateTime('not-a-date')).toBe('not-a-date')
  })
})
