/**
 * Admin Audit tests — filterable, paginated audit list (contract §2 #13).
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminAuditPage } from './Audit'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const EVENTS = {
  items: [
    {
      id: 'ev-1',
      actor_user_id: 'aaaaaaaa-1111-1111-1111-111111111111',
      action: 'user_disabled',
      target_type: 'user',
      target_id: 'bbbbbbbb-2222-2222-2222-222222222222',
      created_at: '2026-11-22T01:00:00Z',
      reason: 'spam',
      outcome: 'success',
      details: null,
    },
    {
      id: 'ev-2',
      actor_user_id: 'aaaaaaaa-1111-1111-1111-111111111111',
      action: 'recipe_published',
      target_type: 'recipe',
      target_id: 'r-1',
      created_at: '2026-11-22T02:00:00Z',
      reason: null,
      outcome: 'failure',
      details: null,
    },
  ],
  total: 2,
}

describe('AdminAuditPage', () => {
  let calls: string[]

  beforeEach(() => {
    window.localStorage.clear()
    calls = []
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function stubFetch(events: unknown = EVENTS) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        calls.push(url)
        if (url.startsWith('/api/v2/admin/audit-events'))
          return Promise.resolve(jsonResponse(events))
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  }

  function renderPage() {
    return render(
      <MemoryRouter>
        <AdminAuditPage />
      </MemoryRouter>,
    )
  }

  it('lists events with actor, action, target, outcome and reason', async () => {
    stubFetch()
    renderPage()
    expect(await screen.findByText('user_disabled')).toBeDefined()
    expect(screen.getByText('recipe_published')).toBeDefined()
    expect(screen.getByText('成功')).toBeDefined()
    expect(screen.getByText('失败')).toBeDefined()
    expect(screen.getByText('spam')).toBeDefined()
    expect(screen.getByText('user:bbbbbbbb')).toBeDefined()
  })

  it('filters send action + target_id + date range', async () => {
    stubFetch()
    renderPage()
    await screen.findByText('user_disabled')
    fireEvent.change(screen.getByLabelText('操作'), {
      target: { value: 'user_disabled' },
    })
    fireEvent.change(screen.getByLabelText('对象 ID'), {
      target: { value: 'u-2' },
    })
    fireEvent.change(screen.getByLabelText('开始日期'), {
      target: { value: '2026-11-01' },
    })
    fireEvent.change(screen.getByLabelText('结束日期'), {
      target: { value: '2026-11-22' },
    })
    fireEvent.click(screen.getByRole('button', { name: '筛选' }))
    await waitFor(() => {
      const url = new URL(calls[calls.length - 1], 'http://localhost')
      expect(url.searchParams.get('action')).toBe('user_disabled')
      expect(url.searchParams.get('target_id')).toBe('u-2')
      expect(url.searchParams.get('from')).toBe('2026-11-01')
      expect(url.searchParams.get('to')).toBe('2026-11-22')
    })
  })

  it('empty audit → honest empty state, no edit/delete actions', async () => {
    stubFetch({ items: [], total: 0 })
    renderPage()
    expect(await screen.findByText('暂无操作记录')).toBeDefined()
    expect(screen.queryByRole('button', { name: '编辑' })).toBeNull()
    expect(screen.queryByRole('button', { name: '删除' })).toBeNull()
  })
})
