import { cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppShell } from './AppShell'
import {
  STORAGE_KEYS,
  resetAuthState,
  setStoredUserName,
  setTokens,
} from '../lib/auth'

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/app/upload']}>
      <AppShell />
    </MemoryRouter>,
  )
}

function topbarUserText(): string | null {
  return document.querySelector('.app-topbar-user')?.textContent ?? null
}

describe('AppShell topbar display name (Phase 4)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  // @testing-library/react only auto-registers cleanup when vitest
  // globals are on; this config uses globals: false, so clean up
  // explicitly — otherwise renders accumulate and queries go ambiguous.
  afterEach(() => {
    cleanup()
  })

  it('shows the stored display name', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    expect(topbarUserText()).toBe('小明')
  })

  it('missing name → email local part, never the full email', () => {
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderShell()
    expect(topbarUserText()).toBe('lam')
  })

  it('logged in with nothing stored → plain 用户, no UUID', () => {
    setTokens('access-1', 'refresh-1')
    renderShell()
    expect(topbarUserText()).toBe('用户')
  })

  it('logged out with nothing stored → 未登录', () => {
    renderShell()
    expect(topbarUserText()).toBe('未登录')
  })

  it('never shows a UUID from the JWT', () => {
    // A real JWT whose sub is a UUID-like id; the topbar must not
    // render any part of it.
    const uuid = '11111111-2222-3333-4444-555555555555'
    const payload = btoa(JSON.stringify({ sub: uuid, exp: 9999999999 }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    setTokens(`header.${payload}.sig`, 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    expect(topbarUserText()).toBe('小明')
    expect(topbarUserText()).not.toContain(uuid)
    expect(topbarUserText()).not.toContain('11111111')
  })
})
