/**
 * Component test — Transactions page (FE-03): list + read-only receipt rows.
 * (Form submit đã test ở ExpenseForm.test.tsx; service đã test ở
 * transactions.test.ts.)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import Transactions from './index'
import { taroMock, __resetTaroStorage } from '../../test/taroMock'
import { STORAGE_KEYS } from '../../services/auth'
import { useSessionStore } from '../../store/session'
import type { Transaction } from '../../services/transactions'

const household = {
  id: 'h-1',
  name: '家',
  default_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  locale: 'zh-CN',
  created_at: null,
  role: 'owner',
}

const manualTx: Transaction = {
  id: 'tx-1',
  household_id: 'h-1',
  receipt_id: null,
  type: 'expense',
  amount: 86.5,
  currency: 'CNY',
  category: 'food',
  occurred_at: '2026-11-21T10:00:00+08:00',
  note: '午饭',
  created_at: '2026-11-21T10:00:00+08:00',
  updated_at: '2026-11-21T10:00:00+08:00',
}

const receiptTx: Transaction = {
  ...manualTx,
  id: 'tx-2',
  receipt_id: 'rc-1',
  amount: 132,
  note: '超市购物',
}

function renderTransactions() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<Transactions />, { wrapper })
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
  taroMock.request.mockImplementation(async (opts: { url: string }) => {
    const url = opts.url
    if (url.includes('/households')) return { statusCode: 200, data: [household] }
    if (url.includes('/transactions')) return { statusCode: 200, data: [manualTx, receiptTx] }
    return { statusCode: 200, data: [] }
  })
})

afterEach(() => {
  cleanup()
  useSessionStore.setState({ isLoggedIn: false, user: null, currentHouseholdId: null, households: [] })
})

describe('Transactions page', () => {
  it('list: số tiền formatAmount (¥86.5, ¥132), chip 小票 chỉ ở dòng từ hoá đơn', async () => {
    renderTransactions()
    // Chờ text phụ thuộc dữ liệu — '最近记账' là header tĩnh, render cả khi
    // list chưa về nên không dùng nó để chờ.
    expect(await screen.findByText('午饭')).toBeTruthy()
    expect(screen.getByText('超市购物')).toBeTruthy()
    expect(screen.getByText('¥86.5')).toBeTruthy()
    expect(screen.getByText('¥132')).toBeTruthy()
    expect(screen.getByText('小票')).toBeTruthy()
    expect(screen.getByText(/来自小票/)).toBeTruthy()
  })

  it('bấm dòng chi tay → mở dialog 编辑记账', async () => {
    renderTransactions()
    await screen.findByText('午饭')
    fireEvent.click(screen.getByText('午饭'))
    expect(await screen.findByText('编辑记账')).toBeTruthy()
    expect(screen.getByText('删除这笔记账')).toBeTruthy()
  })

  it('bấm dòng từ hoá đơn → KHÔNG mở dialog (chỉ đọc, PATCH/DELETE sẽ 409)', async () => {
    renderTransactions()
    await screen.findByText('超市购物')
    fireEvent.click(screen.getByText('超市购物'))
    await waitFor(() => expect(taroMock.request).toHaveBeenCalled())
    expect(screen.queryByText('编辑记账')).toBeNull()
  })

  it('mobile: không render bảng desktop (không có header 操作 / nút 编辑)', async () => {
    renderTransactions()
    await screen.findByText('午饭')
    expect(screen.queryByText('操作')).toBeNull()
    expect(screen.queryByText('编辑')).toBeNull()
  })
})

/** Controllable window.matchMedia — desktop (matches:true), cùng shape với setup.ts. */
function mockMatchMediaDesktop(): void {
  const createMql = () => ({
    matches: true,
    media: '(min-width: 1024px)',
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
  window.matchMedia = vi.fn(createMql) as unknown as typeof window.matchMedia
}

describe('Transactions page — desktop (FE-04)', () => {
  const originalMatchMedia = window.matchMedia

  beforeEach(() => {
    mockMatchMediaDesktop()
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('desktop render bảng (đủ 6 cột) thay vì list mobile', async () => {
    renderTransactions()
    await screen.findByText('午饭')
    // Dialog sửa (đang đóng) vẫn render label 日期/分类/金额/备注 trong DOM
    // nên getByText trùng — header bảng là match có display: table-cell.
    for (const header of ['日期', '分类', '金额', '备注', '类型', '操作']) {
      const matches = screen.getAllByText(header)
      expect(matches.some((el) => (el as HTMLElement).style.display === 'table-cell')).toBe(true)
    }
    // Nút 编辑/删除 chỉ có ở bảng desktop (list mobile mở dialog bằng bấm dòng).
    expect(screen.getAllByText('编辑').length).toBe(1)
    expect(screen.getAllByText('删除').length).toBe(1)
  })

  it('desktop: bấm 编辑 ở bảng mở dialog 编辑记账', async () => {
    renderTransactions()
    await screen.findByText('午饭')
    fireEvent.click(screen.getByText('编辑'))
    expect(await screen.findByText('编辑记账')).toBeTruthy()
  })

  it('desktop: bấm 删除 ở bảng mở dialog sửa (flow xoá hiện có)', async () => {
    renderTransactions()
    await screen.findByText('午饭')
    fireEvent.click(screen.getByText('删除'))
    expect(await screen.findByText('编辑记账')).toBeTruthy()
    expect(screen.getByText('删除这笔记账')).toBeTruthy()
  })
})
