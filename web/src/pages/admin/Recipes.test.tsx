/**
 * Admin Recipes tests — seed list incl. drafts + hidden, create,
 * publish / hide / republish (contract §2 #10–#12).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminRecipesPage } from './Recipes'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const LIST = {
  items: [
    {
      id: 'r-1',
      title: 'Phở bò',
      status: 'published',
      author: 'Món Ngon',
      source_url: 'https://example.com/pho',
      category: '汤',
      language: 'vi',
      updated_at: '2026-11-22T00:00:00Z',
    },
    {
      id: 'r-2',
      title: '红烧肉',
      status: 'draft',
      author: null,
      source_url: null,
      category: '肉',
      language: 'zh',
      updated_at: '2026-11-21T00:00:00Z',
    },
    {
      id: 'r-3',
      title: 'Hidden Soup',
      status: 'hidden',
      author: 'Test',
      source_url: null,
      category: null,
      language: 'en',
      updated_at: '2026-11-20T00:00:00Z',
    },
  ],
  total: 3,
}

describe('AdminRecipesPage', () => {
  let calls: { url: string; init?: RequestInit }[]

  beforeEach(() => {
    window.localStorage.clear()
    calls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, init })
        if (url.startsWith('/api/v2/admin/recipes')) {
          if (init?.method === 'POST' || init?.method === 'PATCH') {
            return Promise.resolve(
              jsonResponse({
                id: 'r-9',
                title: 'New',
                status: 'draft',
                author: null,
                source_url: null,
                category: null,
                language: null,
                updated_at: '2026-11-22T00:00:00Z',
              }),
            )
          }
          return Promise.resolve(jsonResponse(LIST))
        }
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function renderPage() {
    return render(
      <MemoryRouter>
        <AdminRecipesPage />
      </MemoryRouter>,
    )
  }

  it('lists drafts + hidden + published, with status and author', async () => {
    renderPage()
    expect(await screen.findByText(/Phở bò/)).toBeDefined()
    expect(screen.getByText('红烧肉')).toBeDefined()
    expect(screen.getByText('Hidden Soup')).toBeDefined()
    // Status words also appear in the filter <option>s, so scope to
    // the table itself.
    const table = screen.getByRole('table')
    expect(within(table).getByText('已发布')).toBeDefined()
    expect(within(table).getByText('草稿')).toBeDefined()
    expect(within(table).getByText('已隐藏')).toBeDefined()
    expect(screen.getByText('Món Ngon')).toBeDefined()
  })

  it('status filter sends status=draft', async () => {
    renderPage()
    await screen.findByText(/Phở bò/)
    fireEvent.change(screen.getByLabelText('状态'), {
      target: { value: 'draft' },
    })
    await waitFor(() => {
      const url = new URL(calls[calls.length - 1].url, 'http://localhost')
      expect(url.searchParams.get('status')).toBe('draft')
    })
  })

  it('create requires a title, then POSTs without a status', async () => {
    renderPage()
    await screen.findByText(/Phở bò/)
    fireEvent.click(screen.getByRole('button', { name: '新建菜谱' }))
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('请填写标题')).toBeDefined()
    expect(calls.some((c) => c.init?.method === 'POST')).toBe(false)
    fireEvent.change(screen.getByLabelText('标题'), {
      target: { value: 'Canh chua' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => {
      const post = calls.find((c) => c.init?.method === 'POST')
      expect(post).toBeDefined()
      const body = JSON.parse(post?.init?.body as string) as Record<string, unknown>
      expect(body.title).toBe('Canh chua')
      expect('status' in body).toBe(false)
    })
  })

  it('publish on a draft PATCHes status=published; hide on published PATCHes hidden', async () => {
    renderPage()
    await screen.findByText(/Phở bò/)
    // Draft row: 发布 button.
    fireEvent.click(screen.getAllByRole('button', { name: '发布' })[0])
    await waitFor(() => {
      const patch = calls.find(
        (c) => c.init?.method === 'PATCH' && c.url.includes('/r-2'),
      )
      expect(patch).toBeDefined()
      expect(JSON.parse(patch?.init?.body as string)).toEqual({
        status: 'published',
      })
    })
    // Published row: 隐藏 button.
    fireEvent.click(screen.getAllByRole('button', { name: '隐藏' })[0])
    await waitFor(() => {
      const patch = calls.find(
        (c) => c.init?.method === 'PATCH' && c.url.includes('/r-1'),
      )
      expect(patch).toBeDefined()
      expect(JSON.parse(patch?.init?.body as string)).toEqual({ status: 'hidden' })
    })
    // Hidden row offers 重新发布, not 发布.
    expect(screen.getByRole('button', { name: '重新发布' })).toBeDefined()
  })

  it('empty list → honest empty state "No recipes yet." in English', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ items: [], total: 0 }))),
    )
    renderPage()
    expect(await screen.findByText('还没有菜谱。')).toBeDefined()
  })
})
