/**
 * Unit tests — transactions.ts: API paths + validateAmountText + category labels.
 * Pattern theo receipts.test.ts (mock Taro.request qua taroMock).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { taroMock, __resetTaroStorage } from '../test/taroMock'
import {
  CATEGORY_LABELS,
  CURRENCY_LABELS,
  createTransaction,
  deleteTransaction,
  getSpendingSummary,
  isManualTransaction,
  listTransactions,
  patchTransaction,
  validateAmountText,
  type Transaction,
} from './transactions'
import { STORAGE_KEYS } from './auth'

const manualTx: Transaction = {
  id: 'tx-1',
  household_id: 'h-1',
  receipt_id: null,
  type: 'expense',
  amount: 86.5,
  currency: 'CNY',
  category: 'food',
  occurred_at: '2026-11-21T00:00:00+08:00',
  note: '午饭',
  created_at: '2026-11-21T10:00:00+08:00',
  updated_at: '2026-11-21T10:00:00+08:00',
}

const receiptTx: Transaction = { ...manualTx, id: 'tx-2', receipt_id: 'rc-1' }

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-valid')
})

describe('transactions API paths', () => {
  it('listTransactions: household_id + limit mặc định 50', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 200, data: [] })
    await listTransactions('h-1')
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({ url: expect.stringContaining('/api/v2/transactions?household_id=h-1') }),
    )
    const url = (taroMock.request.mock.calls[0][0] as { url: string }).url
    expect(url).toContain('limit=50')
    expect(url).toContain('offset=0')
  })
  it('listTransactions: filter currency + category + from/to đi kèm query', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 200, data: [] })
    await listTransactions('h-1', {
      currency: 'VND',
      category: 'food',
      from: '2026-11-01T00:00:00+08:00',
      to: '2026-12-01T00:00:00+08:00',
    })
    const url = (taroMock.request.mock.calls[0][0] as { url: string }).url
    expect(url).toContain('currency=VND')
    expect(url).toContain('category=food')
    expect(url).toContain('from=2026-11-01T00%3A00%3A00%2B08%3A00')
  })
  it('createTransaction: POST /transactions, body KHÔNG có receipt_id (extra=forbid — gửi là 422)', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 201, data: manualTx })
    await createTransaction({
      household_id: 'h-1',
      type: 'expense',
      amount: 86.5,
      currency: 'CNY',
      category: 'food',
      occurred_at: '2026-11-21T00:00:00+08:00',
      note: '午饭',
    })
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({ method: 'POST', url: expect.stringContaining('/api/v2/transactions') }),
    )
    const body = (taroMock.request.mock.calls[0][0] as { data: Record<string, unknown> }).data
    expect(body).not.toHaveProperty('receipt_id')
    expect(body.type).toBe('expense')
  })
  it('patchTransaction: PATCH /transactions/{id}', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 200, data: manualTx })
    await patchTransaction('tx-1', { amount: 90, note: '晚饭' })
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({ method: 'PATCH', url: expect.stringContaining('/api/v2/transactions/tx-1') }),
    )
  })
  it('deleteTransaction: DELETE /transactions/{id}', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 204, data: '' })
    await deleteTransaction('tx-1')
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({ method: 'DELETE', url: expect.stringContaining('/api/v2/transactions/tx-1') }),
    )
  })
})

describe('getSpendingSummary — currency bắt buộc, không cộng trộn tiền', () => {
  it('luôn gửi currency; from/to đi kèm', async () => {
    taroMock.request.mockResolvedValue({
      statusCode: 200,
      data: { currency: 'CNY', total: 100, by_category: [], by_month: [] },
    })
    const res = await getSpendingSummary('h-1', 'CNY', {
      from: '2026-11-01T00:00:00+08:00',
      to: '2026-12-01T00:00:00+08:00',
    })
    const url = (taroMock.request.mock.calls[0][0] as { url: string }).url
    expect(url).toContain('/api/v2/spending/summary?')
    expect(url).toContain('currency=CNY')
    expect(url).toContain('household_id=h-1')
    expect(res.total).toBe(100)
  })
})

describe('isManualTransaction — chỉ chi tay mới sửa/xoá được', () => {
  it('receipt_id null → manual; có receipt_id → chỉ đọc (PATCH/DELETE → 409)', () => {
    expect(isManualTransaction(manualTx)).toBe(true)
    expect(isManualTransaction(receiptTx)).toBe(false)
  })
})

describe('category labels — zh-CN, đúng 4 giá trị backend', () => {
  it('food/household/maintenance/other đều có nhãn, không thêm category', () => {
    expect(Object.keys(CATEGORY_LABELS).sort()).toEqual(['food', 'household', 'maintenance', 'other'])
    expect(CATEGORY_LABELS.food).toBe('餐饮')
    expect(CATEGORY_LABELS.household).toBe('日用')
    expect(CATEGORY_LABELS.maintenance).toBe('维修保养')
    expect(CATEGORY_LABELS.other).toBe('其他')
    expect(CURRENCY_LABELS.CNY).toBe('人民币')
    expect(CURRENCY_LABELS.VND).toBe('越南盾')
  })
})

describe('validateAmountText — form 记账', () => {
  it('rỗng → 请输入金额', () => {
    expect(validateAmountText('')).toBe('请输入金额')
    expect(validateAmountText('   ')).toBe('请输入金额')
  })
  it('không phải số → 请输入正确的金额', () => {
    expect(validateAmountText('abc')).toBe('请输入正确的金额')
    expect(validateAmountText('12a')).toBe('请输入正确的金额')
  })
  it('quá 2 chữ số thập phân → 金额最多保留两位小数', () => {
    expect(validateAmountText('100.005')).toBe('金额最多保留两位小数')
  })
  it('0 / âm → 金额必须大于 0 (backend Decimal gt=0)', () => {
    expect(validateAmountText('0')).toBe('金额必须大于 0')
    expect(validateAmountText('0.00')).toBe('金额必须大于 0')
    expect(validateAmountText('-5')).toBe('金额必须大于 0')
  })
  it('hợp lệ → null', () => {
    expect(validateAmountText('100')).toBe(null)
    expect(validateAmountText('100.5')).toBe(null)
    expect(validateAmountText('0.1')).toBe(null)
  })
})
