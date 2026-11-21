/**
 * Knowledge page tests (Wave 3 fix for plan §6.3):
 * - logged-out visitors are sent to /login (the endpoint needs auth);
 * - logged-in search shows results with their source citation;
 * - no match above the threshold shows the honest empty state and
 *   never a fabricated shelf-life figure;
 * - no ?q= shows the hint and fires no request.
 *
 * NOTE: this project has no jest-dom matchers, so assertions use plain
 * vitest (`textContent`) instead of `toHaveTextContent`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { LanguageProvider } from '../lib/LanguageProvider'
import type { KnowledgeResult } from '../lib/knowledge'

const { mockIsLoggedIn, mockSearch } = vi.hoisted(() => ({
  mockIsLoggedIn: vi.fn(),
  mockSearch: vi.fn(),
}))
vi.mock('../lib/auth', () => ({
  isLoggedIn: mockIsLoggedIn,
  loginWithEmail: vi.fn(),
  logout: vi.fn(),
  ApiError: class MockApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))
vi.mock('../lib/knowledge', () => ({
  searchKnowledge: mockSearch,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  window.localStorage.clear()
  mockIsLoggedIn.mockReturnValue(false)
  mockSearch.mockResolvedValue([])
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

const EGG_ROWS: KnowledgeResult[] = [
  {
    title: '鸡蛋（冷藏）',
    source: 'USDA FoodKeeper',
    content: '鸡蛋冷藏保存 3-5 周。',
    score: 0.9,
  },
]

describe('/knowledge', () => {
  it('logged-out visitor is sent to /login', () => {
    renderAt('/knowledge?q=%E9%B8%A1%E8%9B%8B')
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
    expect(mockSearch).not.toHaveBeenCalled()
  })

  it('logged-in search shows results with the source citation', async () => {
    mockIsLoggedIn.mockReturnValue(true)
    mockSearch.mockResolvedValueOnce(EGG_ROWS)
    renderAt('/knowledge?q=%E9%B8%A1%E8%9B%8B')
    await waitFor(() => {
      expect(screen.getByText('鸡蛋（冷藏）')).toBeDefined()
    })
    expect(screen.getByText('来源：USDA FoodKeeper')).toBeDefined()
    expect(screen.getByText('鸡蛋冷藏保存 3-5 周。')).toBeDefined()
    expect(mockSearch).toHaveBeenCalledWith('鸡蛋')
  })

  it('no match shows the honest empty state, never a shelf-life figure', async () => {
    mockIsLoggedIn.mockReturnValue(true)
    mockSearch.mockResolvedValueOnce([])
    renderAt('/knowledge?q=%E9%BE%99%E8%82%89')
    await waitFor(() => {
      expect(screen.getByText('未找到相关知识')).toBeDefined()
    })
    expect(
      screen.getByText(/知识库中暂无与「龙肉」相关的内容/),
    ).toBeDefined()
  })

  it('no ?q= shows the hint and fires no request', () => {
    mockIsLoggedIn.mockReturnValue(true)
    renderAt('/knowledge')
    expect(screen.getByText('输入食材名称开始查询')).toBeDefined()
    expect(mockSearch).not.toHaveBeenCalled()
  })

  it('switching to Vietnamese renders the knowledge page in Vietnamese (Phase 4, F-02)', async () => {
    mockIsLoggedIn.mockReturnValue(true)
    render(
      <LanguageProvider>
        <MemoryRouter initialEntries={['/knowledge']}>
          <AppRoutes />
        </MemoryRouter>
      </LanguageProvider>,
    )
    expect(
      await screen.findByRole('heading', { name: '知识查询' }),
    ).toBeDefined()
    fireEvent.change(screen.getByLabelText('语言'), {
      target: { value: 'vi' },
    })
    expect(
      await screen.findByRole('heading', { name: 'Tra cứu kiến thức' }),
    ).toBeDefined()
    expect(
      screen.getByText('Nhập tên nguyên liệu để bắt đầu tra cứu'),
    ).toBeDefined()
  })

  it('a failed search shows the error panel', async () => {
    mockIsLoggedIn.mockReturnValue(true)
    mockSearch.mockRejectedValueOnce(new Error('boom'))
    renderAt('/knowledge?q=%E9%B8%A1%E8%9B%8B')
    await waitFor(() => {
      expect(screen.getByText('查询失败，请检查网络后重试。')).toBeDefined()
    })
  })
})
