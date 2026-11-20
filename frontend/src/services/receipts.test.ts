/**
 * Unit tests — receipts.ts: polling state machine (§8.5) + request paths.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { taroMock, __resetTaroStorage } from '../test/taroMock'
import {
  confirmReceipt,
  getReceipt,
  isTerminalStatus,
  listReceipts,
  pollIntervalFor,
} from './receipts'
import { STORAGE_KEYS } from './auth'

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-valid')
})

describe('pollIntervalFor — state machine (§8.5)', () => {
  it('trạng thái terminal dừng refetch', () => {
    expect(pollIntervalFor(0, 'completed')).toBe(false)
    expect(pollIntervalFor(0, 'failed')).toBe(false)
    expect(pollIntervalFor(0, 'needs_review')).toBe(false)
  })
  it('3s trong 60s đầu, 5s sau đó', () => {
    expect(pollIntervalFor(0, 'pending')).toBe(3000)
    expect(pollIntervalFor(59_999, 'processing')).toBe(3000)
    expect(pollIntervalFor(60_000, 'processing')).toBe(5000)
    expect(pollIntervalFor(179_999, 'processing')).toBe(5000)
  })
  it('hard stop ở 300s', () => {
    expect(pollIntervalFor(300_000, 'processing')).toBe(false)
    expect(pollIntervalFor(999_999, 'pending')).toBe(false)
  })
  it('isTerminalStatus', () => {
    expect(isTerminalStatus('pending')).toBe(false)
    expect(isTerminalStatus('processing')).toBe(false)
    expect(isTerminalStatus('completed')).toBe(true)
  })
})

describe('receipts API paths', () => {
  it('listReceipts: household_id + limit mặc định 20', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 200, data: [] })
    await listReceipts('h-1')
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({ url: expect.stringContaining('/api/v2/receipts?') }),
    )
    const url = (taroMock.request.mock.calls[0][0] as { url: string }).url
    expect(url).toContain('household_id=h-1')
    expect(url).toContain('limit=20')
  })

  it('getReceipt: GET /receipts/{id}', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 200, data: { id: 'r-1' } })
    await getReceipt('r-1')
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({ url: expect.stringContaining('/api/v2/receipts/r-1') }),
    )
  })

  it('confirmReceipt: POST body đúng shape, dòng thêm line_id null (D-F3)', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 200, data: { id: 'r-1', status: 'completed' } })
    await confirmReceipt('r-1', [
      { line_id: 'l-1', quantity: 2, unit: '瓶', price: 4, is_stock_item: true },
      { line_id: null, quantity: 1, unit: '个', price: 3.5, is_stock_item: true },
    ])
    const call = taroMock.request.mock.calls[0][0] as { method: string; data: unknown }
    expect(call.method).toBe('POST')
    expect(call.data).toEqual({
      lines: [
        { line_id: 'l-1', quantity: 2, unit: '瓶', price: 4, is_stock_item: true },
        { line_id: null, quantity: 1, unit: '个', price: 3.5, is_stock_item: true },
      ],
    })
  })
})
