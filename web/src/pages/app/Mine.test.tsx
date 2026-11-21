import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MinePage } from './Mine'
import {
  STORAGE_KEYS,
  resetAuthState,
  setStoredUserName,
  setTokens,
} from '../../lib/auth'

const HOUSEHOLD = {
  id: '11111111-1111-1111-1111-111111111111',
  name: '我家',
  default_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  locale: 'zh-CN',
  created_at: null,
  role: 'owner',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('MinePage display name (Phase 4, F-06b)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/households'))
          return Promise.resolve(jsonResponse([HOUSEHOLD]))
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
        <MinePage />
      </MemoryRouter>,
    )
  }

  it('shows the stored display name, never the raw user id', async () => {
    const uuid = '11111111-2222-3333-4444-555555555555'
    const payload = btoa(JSON.stringify({ sub: uuid, exp: 9999999999 }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    setTokens(`header.${payload}.sig`, 'refresh-1')
    setStoredUserName('小明')
    renderPage()
    expect(await screen.findByText('小明')).toBeDefined()
    expect(document.body.textContent).not.toContain(uuid)
    expect(document.body.textContent).not.toContain('11111111')
  })

  it('missing name → email local part, never the full email or a UUID', async () => {
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderPage()
    expect(await screen.findByText('lam')).toBeDefined()
    // The 用户 row shows the local part; the 邮箱 row still shows the
    // full address (that is its own field, not a leak).
    const values = Array.from(
      document.querySelectorAll('.mine-list dd'),
    ).map((el) => el.textContent)
    expect(values[0]).toBe('lam')
    expect(values[1]).toBe('lam@example.com')
  })
})
