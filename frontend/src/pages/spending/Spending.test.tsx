/**
 * Component test — Spending page (FE-03): tổng tháng + theo danh mục +
 * danh sách các tháng trong năm, một tiền tệ tại một thời điểm.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import Spending from './index'
import { taroMock, __resetTaroStorage } from '../../test/taroMock'
import { STORAGE_KEYS } from '../../services/auth'
import { useSessionStore } from '../../store/session'
import { currentMonth, monthLabel, monthRange, shiftMonth, yearRange } from '../../utils/format'

const household = {
  id: 'h-1',
  name: '家',
  default_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  locale: 'zh-CN',
  created_at: null,
  role: 'owner',
}

function renderSpending() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<Spending />, { wrapper })
}

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-valid')
  useSessionStore.setState({
    isLoggedIn: true,
    user: { id: 'u-1' },
    currentHouseholdId: 'h-1',
    households: [{ id: 'h-1', name: '家' }],
  })
  const thisMonth = currentMonth('Asia/Shanghai')
  const prevMonth = shiftMonth(thisMonth, -1)
  taroMock.request.mockImplementation(async (opts: { url: string }) => {
    const url = opts.url
    if (url.includes('/households')) return { statusCode: 200, data: [household] }
    if (url.includes('/spending/summary')) {
      // Tháng hiện tại: tổng 286.5, food 200 + household 86.5.
      // Khớp theo `from=` (không khớp trần — `to` của tháng trước trùng
      // `from` của tháng này, vd to=2026-11-01).
      if (url.includes(`from=${encodeURIComponent(monthRange(thisMonth, 'Asia/Shanghai').from)}`)) {
        return {
          statusCode: 200,
          data: {
            currency: 'CNY',
            total: 286.5,
            by_category: [
              { category: 'food', total: 200 },
              { category: 'household', total: 86.5 },
            ],
            by_month: [{ month: thisMonth, total: 286.5 }],
          },
        }
      }
      // Tháng trước: tổng 150 (dùng khi bấm 上个月).
      if (url.includes(`from=${encodeURIComponent(monthRange(prevMonth, 'Asia/Shanghai').from)}`)) {
        return {
          statusCode: 200,
          data: {
            currency: 'CNY',
            total: 150,
            by_category: [{ category: 'food', total: 150 }],
            by_month: [{ month: prevMonth, total: 150 }],
          },
        }
      }
      // Cả năm: by_month cho danh sách các tháng.
      if (url.includes(`from=${encodeURIComponent(yearRange(2026, 'Asia/Shanghai').from)}`)) {
        return {
          statusCode: 200,
          data: {
            currency: 'CNY',
            total: 436.5,
            by_category: [],
            by_month: [
              { month: thisMonth, total: 286.5 },
              { month: prevMonth, total: 150 },
            ],
          },
        }
      }
      return { statusCode: 200, data: { currency: 'CNY', total: 0, by_category: [], by_month: [] } }
    }
    return { statusCode: 200, data: [] }
  })
})

afterEach(() => {
  cleanup()
  useSessionStore.setState({ isLoggedIn: false, user: null, currentHouseholdId: null, households: [] })
})

describe('Spending page', () => {
  it('tổng tháng hiện tại + breakdown theo danh mục (formatAmount, bỏ số 0 thừa)', async () => {
    const thisMonth = currentMonth('Asia/Shanghai')
    renderSpending()
    // Chờ text phụ thuộc dữ liệu (label '本月支出' render cả khi đang load
    // với total 0 nên không dùng nó để chờ).
    // ¥286.5 xuất hiện 2 lần: card 本月支出 + dòng tháng này trong danh sách năm.
    const totals = await screen.findAllByText('¥286.5')
    expect(totals.length).toBe(2)
    // Nhãn tháng xuất hiện 2 lần: selector tháng + dòng trong danh sách các tháng.
    expect(screen.getAllByText(monthLabel(thisMonth)).length).toBeGreaterThan(0)
    expect(screen.getByText('餐饮')).toBeTruthy()
    expect(screen.getByText('¥200 · 69.81%')).toBeTruthy()
    expect(screen.getByText('日用')).toBeTruthy()
  })

  it('danh sách các tháng trong năm, bấm một tháng để xem tháng đó', async () => {
    const thisMonth = currentMonth('Asia/Shanghai')
    const prevMonth = shiftMonth(thisMonth, -1)
    renderSpending()
    expect(await screen.findByText(monthLabel(prevMonth))).toBeTruthy()
    // Trước khi bấm: ¥150 chỉ có ở dòng tháng trước trong danh sách năm.
    expect(screen.getAllByText('¥150').length).toBe(1)
    fireEvent.click(screen.getByText(monthLabel(prevMonth)))
    // Sau khi bấm: tổng tháng (card 本月支出) cũng thành ¥150 → 2 chỗ.
    await waitFor(() => expect(screen.getAllByText('¥150').length).toBe(2))
  })

  it('nút 上个月 đổi tháng; nút 下个月 disable khi đang ở tháng hiện tại', async () => {
    const thisMonth = currentMonth('Asia/Shanghai')
    renderSpending()
    await screen.findByText('本月支出')
    expect(screen.getByLabelText('下个月').closest('button')).toHaveProperty('disabled', true)
    fireEvent.click(screen.getByLabelText('上个月'))
    // Sau khi đổi tháng, nhãn tháng trước xuất hiện cả ở selector lẫn danh sách các tháng.
    await waitFor(() =>
      expect(screen.getAllByText(monthLabel(shiftMonth(thisMonth, -1))).length).toBeGreaterThan(1),
    )
  })

  it('đổi tiền tệ sang VND → gọi summary với currency=VND (một tiền tệ tại một thời điểm)', async () => {
    renderSpending()
    await screen.findByText('本月支出')
    vi.clearAllMocks()
    fireEvent.click(screen.getByText('越南盾 ₫'))
    await waitFor(() =>
      expect(taroMock.request).toHaveBeenCalledWith(
        expect.objectContaining({ url: expect.stringContaining('currency=VND') }),
      ),
    )
  })
})
