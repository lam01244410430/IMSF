/**
 * Receipt detail tests (Step 5, §5.2/§5.3): Processing checklist/timeout
 * copy, failure, completed, Needs Review form (mismatch card, live summary,
 * confirm payload, validation, 409, delete + undo). D-F2: 重新识别 không
 * xuất hiện ở màn nào. services/receipts được mock (importOriginal cho
 * phần còn lại).
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { taroMock } from '../../test/taroMock'
import ReceiptDetail from './index'
import { useReviewDraftStore } from '../../store/reviewDraft'
import { useUiStore } from '../../store/ui'
import type { ReceiptDetail as ReceiptDetailType, ReceiptLine } from '../../services/receipts'
import { fetchReceiptImageSrc } from '../../services/receipts'

// Chỉ mock fetchReceiptImageSrc (page gọi trực tiếp). getReceipt/
// confirmReceipt KHÔNG mock được qua export — useReceiptPolling gọi hàm
// nội bộ của module nên mock export không chạm tới nó; thay vào đó mock
// Taro.request (xem beforeEach) để service thật chạy.
vi.mock('../../services/receipts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/receipts')>()
  return {
    ...actual,
    fetchReceiptImageSrc: vi.fn(),
  }
})

const mockImage = vi.mocked(fetchReceiptImageSrc)

const line = (over: Partial<ReceiptLine>): ReceiptLine => ({
  id: 'l-1',
  line_no: 1,
  raw_name: '伊利纯牛奶 250ml',
  quantity: 2,
  unit: '个',
  price: 4.0,
  currency: 'CNY',
  canonical_ingredient_id: 'm-1',
  canonical_name: '纯牛奶',
  is_stock_item: true,
  ...over,
})

const detail = (over: Partial<ReceiptDetailType>): ReceiptDetailType => ({
  id: 'r-1',
  household_id: 'hh-1',
  uploaded_by_user_id: 'u-1',
  image_url: 'https://x/1.jpg',
  store_name: '沃尔玛',
  purchased_at: new Date().toISOString(),
  total_amount: 10.0,
  currency: 'CNY',
  status: 'processing',
  ocr_raw_text: null,
  error_message: null,
  processed_at: null,
  created_at: new Date(Date.now() - 42_000).toISOString(),
  updated_at: new Date().toISOString(),
  lines: [
    line({}),
    line({
      id: 'l-2',
      line_no: 2,
      raw_name: '农夫山泉 550ml',
      quantity: 1,
      unit: '瓶',
      price: 3.5,
      canonical_ingredient_id: null,
      canonical_name: null,
    }),
  ],
  inventory_created: 0,
  ...over,
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReceiptDetail />
    </QueryClientProvider>,
  )
}

let currentDetail: ReceiptDetailType
let confirmResponse: ReceiptDetailType | null = null
let confirmStatus = 200

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(taroMock.useRouter).mockReturnValue({ params: { id: 'r-1' } })
  mockImage.mockResolvedValue('/tmp/receipt.jpg')
  useReviewDraftStore.getState().clear()
  useUiStore.setState({ toasts: [] })
  confirmResponse = null
  confirmStatus = 200
  vi.mocked(taroMock.request).mockImplementation(async (opts: unknown) => {
    const url = (opts as { url?: string }).url ?? ''
    if (url.includes('/confirm')) {
      return { statusCode: confirmStatus, data: confirmResponse ?? currentDetail }
    }
    return { statusCode: 200, data: currentDetail }
  })
})

function confirmCall() {
  const calls = vi.mocked(taroMock.request).mock.calls
  const call = calls.find((c) => String((c[0] as { url?: string }).url ?? '').includes('/confirm'))
  return call?.[0] as { url: string; data?: unknown } | undefined
}

afterEach(() => {
  cleanup()
  useReviewDraftStore.getState().clear()
})

describe('Screen 02 — Processing', () => {
  it('shows the 3-step checklist, elapsed time and the leave action', async () => {
    currentDetail = detail({})
    renderPage()
    expect(await screen.findByText('正在识别文字 (OCR)')).toBeTruthy()
    expect(screen.getByText('正在匹配食材')).toBeTruthy()
    expect(screen.getByText('正在核对总价')).toBeTruthy()
    expect(screen.getByText(/已用时 0:4\d/)).toBeTruthy()
    expect(screen.getByText('通常需要 30 秒到 2 分钟，请稍等。')).toBeTruthy()
    expect(screen.getByText('先去看看别的，好了通知我')).toBeTruthy()
    expect(screen.queryByText('重新识别')).toBeNull()
  })

  it('shows the failure panel with the server error_message verbatim', async () => {
    currentDetail = detail({ status: 'failed', error_message: '图片模糊，无法读取文字' })
    renderPage()
    expect(await screen.findByText('识别失败')).toBeTruthy()
    expect(screen.getByText('图片模糊，无法读取文字')).toBeTruthy()
    expect(screen.getByText('重新上传')).toBeTruthy()
    expect(await screen.findByText('查看小票图片')).toBeTruthy()
    expect(screen.queryByText('重新识别')).toBeNull()
  })

  it('shows the completed panel with the inventory count', async () => {
    currentDetail = detail({ status: 'completed', inventory_created: 5 })
    renderPage()
    expect(await screen.findByText('识别完成')).toBeTruthy()
    expect(screen.getByText('已入库 5 件食材')).toBeTruthy()
    expect(screen.getByText('查看冰箱')).toBeTruthy()
  })
})

describe('Screen 03 — Needs Review', () => {
  it('shows the mismatch card, line editor and live summary', async () => {
    currentDetail = detail({ status: 'needs_review' })
    renderPage()
    expect(await screen.findByText('总价对不上，需要您核对')).toBeTruthy()
    expect(screen.getByText(/小票总价 ¥10.00，明细合计 ¥7.50，相差 ¥2.50/)).toBeTruthy()
    expect(screen.getByText('伊利纯牛奶 250ml')).toBeTruthy()
    expect(screen.getByText('农夫山泉 550ml')).toBeTruthy()
    expect(screen.getByText('纯牛奶')).toBeTruthy()
    expect(screen.getByText('未匹配')).toBeTruthy()
    expect(screen.getByText('明细合计 ¥7.50 · 相差 ¥2.50 (25.0%)')).toBeTruthy()
    expect(screen.getByText('确认并入库')).toBeTruthy()
    expect(screen.queryByText('重新识别')).toBeNull()
  })

  it('confirms with line totals (not unit prices) and shows the success panel', async () => {
    currentDetail = detail({ status: 'needs_review' })
    confirmResponse = detail({ status: 'completed', inventory_created: 2 })
    renderPage()
    expect(await screen.findByText('确认并入库')).toBeTruthy()
    fireEvent.click(screen.getByText('确认并入库'))
    await waitFor(() => {
      expect(confirmCall()).toBeTruthy()
    })
    expect(confirmCall()?.data).toEqual({
      lines: [
        { line_id: 'l-1', quantity: 2, unit: '个', price: 4, is_stock_item: true },
        { line_id: 'l-2', quantity: 1, unit: '瓶', price: 3.5, is_stock_item: true },
      ],
    })
    expect(await screen.findByText('已确认并入库')).toBeTruthy()
    expect(screen.getByText('2 件食材已记入冰箱')).toBeTruthy()
    expect(screen.getByText('记账 ¥7.50')).toBeTruthy()
  })

  it('blocks confirm when a quantity is 0 and shows the inline error', async () => {
    currentDetail = detail({ status: 'needs_review' })
    renderPage()
    expect(await screen.findByText('确认并入库')).toBeTruthy()
    const qtyInputs = screen.getAllByLabelText('数量')
    fireEvent.change(qtyInputs[0], { target: { value: '0' } })
    expect(await screen.findByText('数量必须大于 0')).toBeTruthy()
    fireEvent.click(screen.getByText('确认并入库'))
    expect(confirmCall()).toBeUndefined()
    await waitFor(() => {
      expect(useUiStore.getState().toasts.at(-1)?.message).toBe('有 1 项需要修改，请检查标红处')
    })
  })

  it('handles 409 by refetching and toasting the status update', async () => {
    currentDetail = detail({ status: 'needs_review' })
    confirmStatus = 409
    renderPage()
    expect(await screen.findByText('确认并入库')).toBeTruthy()
    const detailCallsBefore = vi
      .mocked(taroMock.request)
      .mock.calls.filter((c) => !String((c[0] as { url?: string }).url ?? '').includes('/confirm')).length
    fireEvent.click(screen.getByText('确认并入库'))
    await waitFor(() => {
      const now = vi
        .mocked(taroMock.request)
        .mock.calls.filter((c) => !String((c[0] as { url?: string }).url ?? '').includes('/confirm')).length
      expect(now).toBeGreaterThan(detailCallsBefore)
    })
    await waitFor(() => {
      expect(useUiStore.getState().toasts.at(-1)?.message).toBe('小票状态已更新，请查看最新结果')
    })
  })

  it('deletes a line with a 5s undo bar', async () => {
    currentDetail = detail({ status: 'needs_review' })
    renderPage()
    expect(await screen.findByText('伊利纯牛奶 250ml')).toBeTruthy()
    fireEvent.click(screen.getAllByText('删除此行')[0])
    expect(screen.queryByText('伊利纯牛奶 250ml')).toBeNull()
    expect(screen.getByText('已删除 1 行')).toBeTruthy()
    fireEvent.click(screen.getByText('撤销'))
    expect(await screen.findByText('伊利纯牛奶 250ml')).toBeTruthy()
  })
})

/** FE-04 desktop two-column (design doc §12.6). */
function mockMatchMedia(matches: boolean): void {
  const createMql = () => ({
    matches,
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

const originalMatchMedia = window.matchMedia

/** Walk up from el to the direct child of container (the column it sits in). */
function directChildOf(el: HTMLElement, container: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = el
  while (node && node.parentElement !== container) {
    node = node.parentElement as HTMLElement | null
  }
  return node
}

describe('Screen 02 — Processing desktop two-column (FE-04)', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('renders thumbnail + steps side by side on desktop', async () => {
    mockMatchMedia(true)
    currentDetail = detail({})
    renderPage()
    expect(await screen.findByText('正在识别文字 (OCR)')).toBeTruthy()
    await waitFor(() => {
      expect(document.querySelector('img')).toBeTruthy()
    })
    const img = document.querySelector('img') as HTMLImageElement
    const leftCol = img.parentElement as HTMLElement
    const container = leftCol.parentElement as HTMLElement
    expect(container.style.flexDirection).toBe('row')
    expect(container.style.gap).toBe('24px')
    expect(leftCol.style.width).toBe('480px')
    const steps = screen.getByText('正在识别文字 (OCR)')
    const rightCol = directChildOf(steps, container)
    expect(rightCol).toBeTruthy()
    expect(rightCol).not.toBe(leftCol)
  })

  it('keeps the single column on mobile', async () => {
    mockMatchMedia(false)
    currentDetail = detail({})
    renderPage()
    expect(await screen.findByText('正在识别文字 (OCR)')).toBeTruthy()
    await waitFor(() => {
      expect(document.querySelector('img')).toBeTruthy()
    })
    const img = document.querySelector('img') as HTMLImageElement
    const container = img.parentElement?.parentElement as HTMLElement
    expect(container.style.flexDirection).toBe('column')
  })
})

describe('Screen 03 — Needs Review desktop two-column (FE-04)', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('renders image + lines in a row container with a non-fixed action bar on desktop', async () => {
    mockMatchMedia(true)
    currentDetail = detail({ status: 'needs_review' })
    renderPage()
    expect(await screen.findByText('总价对不上，需要您核对')).toBeTruthy()
    await waitFor(() => {
      expect(document.querySelector('img')).toBeTruthy()
    })
    const img = document.querySelector('img') as HTMLImageElement
    const leftCol = img.parentElement?.parentElement?.parentElement as HTMLElement
    const container = leftCol.parentElement as HTMLElement
    expect(container.style.flexDirection).toBe('row')
    expect(container.style.gap).toBe('24px')
    expect(leftCol.style.width).toBe('480px')
    const lineText = screen.getByText('伊利纯牛奶 250ml')
    const rightCol = directChildOf(lineText, container)
    expect(rightCol).toBeTruthy()
    expect(rightCol).not.toBe(leftCol)
    // Action bar is a normal block at the end of the right column on desktop.
    const confirmBtn = screen.getByText('确认并入库')
    expect((confirmBtn.parentElement as HTMLElement).style.position).toBe('relative')
  })

  it('keeps the fixed action bar and single column on mobile', async () => {
    mockMatchMedia(false)
    currentDetail = detail({ status: 'needs_review' })
    renderPage()
    expect(await screen.findByText('总价对不上，需要您核对')).toBeTruthy()
    await waitFor(() => {
      expect(document.querySelector('img')).toBeTruthy()
    })
    const img = document.querySelector('img') as HTMLImageElement
    const container = img.parentElement?.parentElement?.parentElement?.parentElement as HTMLElement
    expect(container.style.flexDirection).toBe('column')
    const confirmBtn = screen.getByText('确认并入库')
    expect((confirmBtn.parentElement as HTMLElement).style.position).toBe('fixed')
  })
})
