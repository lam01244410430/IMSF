/**
 * Admin Overview tests — counts + actionable exceptions (contract §2 #2).
 * The page is rendered directly (the guard is tested separately in
 * AdminShell.test.tsx); fetch is stubbed per the contract shapes.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminOverviewPage } from './Overview'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const STATS = {
  counts: {
    users: 2,
    households: 1,
    receipts: 3,
    transactions: 4,
    inventory_items: 5,
    published_recipes: 6,
    draft_recipes: 1,
    hidden_recipes: 0,
  },
  exceptions: {
    failed_receipt_jobs: 2,
    overdue_cron: true,
    unavailable_dependencies: ['gpu'],
  },
}

function stubFetch(stats: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.startsWith('/api/v2/admin/stats'))
        return Promise.resolve(jsonResponse(stats, status))
      return Promise.resolve(jsonResponse(null, 404))
    }),
  )
}

describe('AdminOverviewPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function renderPage() {
    return render(
      <MemoryRouter>
        <AdminOverviewPage />
      </MemoryRouter>,
    )
  }

  it('shows operational counts and labels accounts as not-people', async () => {
    stubFetch(STATS)
    renderPage()
    expect(await screen.findByText('总览')).toBeDefined()
    // Count values render as the dashboard total style.
    expect(screen.getByText('2')).toBeDefined()
    expect(screen.getByText('6')).toBeDefined()
    expect(
      screen.getByText('账号不是人数 — 一个人可以有两个账号。'),
    ).toBeDefined()
  })

  it('lists each actionable exception with a link to /admin/system', async () => {
    stubFetch(STATS)
    renderPage()
    const failed = await screen.findByText('小票任务失败 2 个')
    expect(failed.closest('a')?.getAttribute('href')).toBe('/admin/system')
    expect(screen.getByText('定时任务已过期')).toBeDefined()
    expect(screen.getByText('依赖不可用：gpu')).toBeDefined()
  })

  it('no exceptions → honest empty state, no invented problems', async () => {
    stubFetch({
      ...STATS,
      exceptions: {
        failed_receipt_jobs: 0,
        overdue_cron: false,
        unavailable_dependencies: [],
      },
    })
    renderPage()
    expect(await screen.findByText('暂无需要处理的问题')).toBeDefined()
    expect(screen.queryByText(/小票任务失败/)).toBeNull()
  })

  it('stats failure → load error with retry, not an empty dashboard', async () => {
    stubFetch(null, 500)
    renderPage()
    expect(await screen.findByText('加载失败，请检查网络后重试。')).toBeDefined()
    expect(screen.getByRole('button', { name: '重试' })).toBeDefined()
  })
})
