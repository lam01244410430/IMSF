/**
 * Upload page tests (Step 4, §5.1): recent list (rows/empty/error), pick flow
 * → navigateTo receipt, validation error inline. services/receipts +
 * services/upload được mock — test chỉ kiểm tra UI flow, không gọi Taro thật.
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { taroMock } from '../../test/taroMock'
import Upload from './index'
import { useSessionStore } from '../../store/session'
import { useUploadDraftStore } from '../../store/uploadDraft'
import type { Receipt } from '../../services/receipts'
import { listReceipts } from '../../services/receipts'
import { pickImage, preparePickedImage, uploadReceipt } from '../../services/upload'

vi.mock('../../services/receipts', () => ({
  listReceipts: vi.fn(),
}))
vi.mock('../../services/upload', () => ({
  pickImage: vi.fn(),
  preparePickedImage: vi.fn(),
  uploadReceipt: vi.fn(),
  // uploadDraft store thật import newIdempotencyKey từ module này.
  newIdempotencyKey: () => 'test-idempotency-key',
  IMAGE_ERROR_ZH: {
    type: '图片格式不支持，请选择 JPG、PNG 或 WebP',
    size: '图片超过 10 MB，请选择更小的图片',
    unreadable: '无法读取图片，请重新选择',
  },
}))

const mockList = vi.mocked(listReceipts)
const mockPick = vi.mocked(pickImage)
const mockPrepare = vi.mocked(preparePickedImage)
const mockUpload = vi.mocked(uploadReceipt)

const receipt = (id: string, store: string, status: Receipt['status'] = 'completed'): Receipt => ({
  id,
  household_id: 'hh-1',
  uploaded_by_user_id: 'u-1',
  image_url: 'https://x/1.jpg',
  store_name: store,
  purchased_at: new Date().toISOString(),
  total_amount: 123.45,
  currency: 'CNY',
  status,
  ocr_raw_text: null,
  error_message: null,
  processed_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Upload />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  useSessionStore.setState({
    user: { id: 'u-1', wechat_openid: 'o-1' },
    households: [{ id: 'hh-1', name: '家' }],
    isLoggedIn: true,
    currentHouseholdId: 'hh-1',
  })
})

afterEach(() => {
  cleanup()
  useUploadDraftStore.getState().clear()
  useSessionStore.getState().clearSession()
})

describe('Upload page — recent list', () => {
  it('renders the first 3 receipts and a 查看全部 link', async () => {
    mockList.mockResolvedValue([
      receipt('r-1', '沃尔玛'),
      receipt('r-2', '永辉超市', 'needs_review'),
      receipt('r-3', '盒马', 'processing'),
    ])
    renderPage()
    expect(await screen.findByText('沃尔玛')).toBeTruthy()
    expect(screen.getByText('永辉超市')).toBeTruthy()
    expect(screen.getByText('盒马')).toBeTruthy()
    expect(screen.getByText('查看全部 ›')).toBeTruthy()
    expect(screen.getByText('最近小票')).toBeTruthy()
  })

  it('shows the empty state when there are no receipts', async () => {
    mockList.mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('还没有小票')).toBeTruthy()
    expect(screen.getByText('立即拍照')).toBeTruthy()
  })

  it('shows the error panel and retries', async () => {
    mockList.mockRejectedValueOnce(new Error('network down'))
    mockList.mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('加载失败，请检查网络后重试')).toBeTruthy()
    fireEvent.click(screen.getByText('重试'))
    expect(await screen.findByText('还没有小票')).toBeTruthy()
    expect(mockList).toHaveBeenCalledTimes(2)
  })
})

describe('Upload page — pick flow', () => {
  it('picks, uploads and navigates to the receipt on 202', async () => {
    mockList.mockResolvedValue([])
    mockPick.mockResolvedValue({ tempFilePath: '/tmp/a.jpg', size: 100, name: 'a.jpg' })
    mockPrepare.mockResolvedValue({ ok: true, file: { tempFilePath: '/tmp/a.jpg', size: 100, name: 'a.jpg' } })
    mockUpload.mockResolvedValue({ receiptId: 'r-1', status: 'pending' })
    renderPage()
    expect(await screen.findByText('还没有小票')).toBeTruthy()
    fireEvent.click(screen.getByText('拍照'))
    await waitFor(() => {
      expect(mockUpload).toHaveBeenCalledTimes(1)
    })
    expect(mockUpload).toHaveBeenCalledWith(
      expect.objectContaining({ tempFilePath: '/tmp/a.jpg', householdId: 'hh-1' }),
    )
    await waitFor(() => {
      expect(taroMock.navigateTo).toHaveBeenCalledWith({ url: '/pages/receipt/index?id=r-1' })
    })
  })

  it('shows the validation error inline with 重新选择', async () => {
    mockList.mockResolvedValue([])
    mockPick.mockResolvedValue({ tempFilePath: '/tmp/big.jpg', size: 20_000_000, name: 'big.jpg' })
    mockPrepare.mockResolvedValue({ ok: false, error: 'size' })
    renderPage()
    expect(await screen.findByText('还没有小票')).toBeTruthy()
    fireEvent.click(screen.getByText('拍照'))
    expect(await screen.findByText('图片超过 10 MB，请选择更小的图片')).toBeTruthy()
    expect(screen.getByText('重新选择')).toBeTruthy()
    expect(mockUpload).not.toHaveBeenCalled()
  })
})

/** FE-04 desktop two-column (design doc §12.6): capture left, recent right. */
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

describe('Upload page — desktop two-column (FE-04)', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('renders capture + recent in a row container on desktop', async () => {
    mockMatchMedia(true)
    mockList.mockResolvedValue([receipt('r-1', '沃尔玛')])
    renderPage()
    expect(await screen.findByText('沃尔玛')).toBeTruthy()
    // Capture caption -> capture card -> left column -> row container.
    const card = screen.getByText('点击拍照').parentElement
    const leftCol = card?.parentElement
    const container = leftCol?.parentElement
    expect(container?.style.flexDirection).toBe('row')
    expect(container?.style.gap).toBe('24px')
    expect(leftCol?.style.width).toBe('480px')
    // Recent section lives in the other (right) column of the same row.
    const rightCol = screen.getByText('最近小票').parentElement?.parentElement?.parentElement?.parentElement
    expect(rightCol).toBeTruthy()
    expect(rightCol).not.toBe(leftCol)
    expect(rightCol?.parentElement).toBe(container)
    expect(rightCol?.style.minWidth).toBe('0px')
  })

  it('renders a single column on mobile', async () => {
    mockMatchMedia(false)
    mockList.mockResolvedValue([receipt('r-1', '沃尔玛')])
    renderPage()
    expect(await screen.findByText('沃尔玛')).toBeTruthy()
    const card = screen.getByText('点击拍照').parentElement
    const container = card?.parentElement?.parentElement
    expect(container?.style.flexDirection).toBe('column')
    expect(container?.style.gap).toBe('16px')
  })
})
