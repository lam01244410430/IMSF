/**
 * Component test — ExpenseForm (FE-03): validation + submit POST.
 * Render qua index (jsdom resolve về implementation H5 — xem primitives.test.tsx).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import ExpenseForm from './ExpenseForm'
import { taroMock, __resetTaroStorage } from '../../test/taroMock'
import { STORAGE_KEYS } from '../../services/auth'
import { todayDate } from '../../utils/format'
import type { Transaction } from '../../services/transactions'

const createdTx: Transaction = {
  id: 'tx-1',
  household_id: 'h-1',
  receipt_id: null,
  type: 'expense',
  amount: 100.5,
  currency: 'CNY',
  category: 'food',
  occurred_at: '2026-11-21T00:00:00+08:00',
  note: '午饭',
  created_at: '2026-11-21T10:00:00+08:00',
  updated_at: '2026-11-21T10:00:00+08:00',
}

function renderForm(onCreated?: (tx: Transaction) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(
    <ExpenseForm householdId='h-1' defaultCurrency='CNY' timezone='Asia/Shanghai' onCreated={onCreated} />,
    { wrapper },
  )
}

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-valid')
})

afterEach(() => {
  cleanup()
})

describe('ExpenseForm', () => {
  it('render mặc định: 金额 + 人民币 ¥ + 餐饮 + ngày hôm nay + nút 记一笔', () => {
    renderForm()
    expect(screen.getByPlaceholderText('请输入金额')).toBeTruthy()
    expect(screen.getByText('人民币 ¥')).toBeTruthy()
    expect(screen.getByText('餐饮')).toBeTruthy()
    expect(screen.getByText(todayDate('Asia/Shanghai'))).toBeTruthy()
    expect(screen.getByText('记一笔')).toBeTruthy()
  })

  it('picker tiền tệ offer đủ 14 tiền tệ (P2-06, D-F7)', async () => {
    renderForm()
    fireEvent.click(screen.getByText('人民币 ¥'))
    // Picker mở (MUI Dialog): nhãn CNY có 2 chỗ (giá trị đã chọn + option).
    await waitFor(() => expect(screen.getAllByText('人民币 ¥').length).toBeGreaterThanOrEqual(2))
    for (const label of [
      '越南盾 ₫',
      '美元 $',
      '欧元 €',
      '港元 HK$',
      '泰铢 ฿',
      '马来西亚林吉特 RM',
      '新加坡元 S$',
      '印度尼西亚盾 Rp',
      '菲律宾比索 ₱',
      '柬埔寨瑞尔 ៛',
      '老挝基普 ₭',
      '缅甸元 K',
      '文莱元 B$',
    ]) {
      expect(screen.getByText(label)).toBeTruthy()
    }
  })

  it('submit khi chưa nhập amount → lỗi 请输入金额, không gọi API', async () => {
    renderForm()
    fireEvent.click(screen.getByText('记一笔'))
    expect(await screen.findByText('请输入金额')).toBeTruthy()
    expect(taroMock.request).not.toHaveBeenCalled()
  })

  it('amount = 0 → lỗi 金额必须大于 0, không gọi API', async () => {
    renderForm()
    fireEvent.change(screen.getByPlaceholderText('请输入金额'), { target: { value: '0' } })
    fireEvent.click(screen.getByText('记一笔'))
    expect(await screen.findByText('金额必须大于 0')).toBeTruthy()
    expect(taroMock.request).not.toHaveBeenCalled()
  })

  it('quá 2 chữ số thập phân → lỗi 金额最多保留两位小数', async () => {
    renderForm()
    fireEvent.change(screen.getByPlaceholderText('请输入金额'), { target: { value: '100.005' } })
    fireEvent.click(screen.getByText('记一笔'))
    expect(await screen.findByText('金额最多保留两位小数')).toBeTruthy()
    expect(taroMock.request).not.toHaveBeenCalled()
  })

  it('submit hợp lệ → POST /transactions, amount đã chuẩn hoá (100.50 → 100.5), type=expense', async () => {
    taroMock.request.mockResolvedValue({ statusCode: 201, data: createdTx })
    const onCreated = vi.fn()
    renderForm(onCreated)
    fireEvent.change(screen.getByPlaceholderText('请输入金额'), { target: { value: '100.50' } })
    fireEvent.change(screen.getByPlaceholderText('比如：午饭'), { target: { value: '午饭' } })
    fireEvent.click(screen.getByText('记一笔'))
    await waitFor(() => expect(taroMock.request).toHaveBeenCalled())
    const body = (taroMock.request.mock.calls[0][0] as { data: Record<string, unknown> }).data
    expect(body.type).toBe('expense')
    expect(body.amount).toBe(100.5)
    expect(body.currency).toBe('CNY')
    expect(body.category).toBe('food')
    expect(body.note).toBe('午饭')
    expect(body).not.toHaveProperty('receipt_id')
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdTx))
  })
})
