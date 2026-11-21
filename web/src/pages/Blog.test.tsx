import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { logout, resetAuthState } from '../lib/auth'

const EMPTY_LIST = { items: [], total: 0, limit: 20, offset: 0 }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mockFetch(handler: (url: string) => Response | Promise<Response>) {
  const fetchMock = vi.fn((input: string | URL | Request) => {
    const url = typeof input === 'string' ? input : String(input)
    return Promise.resolve(handler(url))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

describe('blog list', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
    logout()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('empty state: honest, no link to a posting page', async () => {
    mockFetch(() => jsonResponse(EMPTY_LIST))
    renderAt('/blog')
    expect(
      await screen.findByRole('heading', { name: '菜谱' }),
    ).toBeDefined()
    expect(await screen.findByText('还没有菜谱')).toBeDefined()
    expect(screen.getByText('第一道菜，等你来分享。')).toBeDefined()
    // Posting is deferred: no link/button leads to a posting page.
    expect(screen.queryByText(/发布菜谱/)).toBeNull()
    expect(screen.queryByText(/写菜谱/)).toBeNull()
  })

  it('search no-match: honest message + clear-filter button', async () => {
    const fetchMock = mockFetch(() => jsonResponse(EMPTY_LIST))
    renderAt('/blog?ingredient=鸡蛋')
    expect(
      await screen.findByText('没有找到使用「鸡蛋」的菜谱'),
    ).toBeDefined()
    // The search actually queried the canonical ingredient.
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      'ingredient=%E9%B8%A1%E8%9B%8B',
    )
    const clear = screen.getByRole('button', { name: '清除筛选' })
    fireEvent.click(clear)
    // Filter cleared -> the plain empty state returns.
    expect(await screen.findByText('还没有菜谱')).toBeDefined()
  })

  it('card meta shows only real fields (no servings, no guessed time)', async () => {
    mockFetch(() =>
      jsonResponse({
        items: [
          {
            id: 'recipe-1',
            title: '番茄炒蛋',
            cover_image: null,
            cook_time: null,
            ingredient_count: 3,
            likes_count: 0,
            created_at: '2026-11-21T10:00:00+00:00',
            author: { id: 'author-1', name: '小林' },
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    )
    renderAt('/blog')
    expect(await screen.findByText('番茄炒蛋')).toBeDefined()
    expect(screen.getByText('3种食材')).toBeDefined()
    // No cook_time on the record -> no 烹饪时间 segment is shown.
    expect(screen.queryByText(/烹饪时间/)).toBeNull()
    // No servings column exists -> the card must never show 人份.
    expect(screen.queryByText(/人份/)).toBeNull()
    expect(screen.getByText('小林')).toBeDefined()
    // Real like count, 0 when none -- never a fake number.
    expect(screen.getByText('0')).toBeDefined()
  })

  it('card with a cover renders the real image', async () => {
    mockFetch(() =>
      jsonResponse({
        items: [
          {
            id: 'recipe-2',
            title: '清蒸鱼',
            cover_image: 'https://example.invalid/cover.jpg',
            cook_time: 25,
            ingredient_count: 2,
            likes_count: 5,
            created_at: '2026-11-21T10:00:00+00:00',
            author: null,
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    )
    renderAt('/blog')
    const img = (await screen.findByAltText('清蒸鱼')) as HTMLImageElement
    expect(img.getAttribute('src')).toBe('https://example.invalid/cover.jpg')
    expect(screen.getByText('烹饪时间 25分钟 · 2种食材')).toBeDefined()
    expect(screen.getByText('5')).toBeDefined()
  })

  it('load error: error panel + retry refetches', async () => {
    const fetchMock = mockFetch(() => {
      throw new Error('network down')
    })
    renderAt('/blog')
    expect(await screen.findByText('加载失败，请检查网络后重试。')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(fetchMock.mock.calls.length).toBeGreaterThan(1)
  })
})
