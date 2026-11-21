/**
 * Theme storage tests (Dashboard Phase A, D2): default light, stored
 * dark wins, invalid stored value falls back to light, storage
 * unavailable falls back to light, and applyTheme maps the stored
 * value to the DaisyUI theme name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  THEME_NAMES,
  THEME_STORAGE_KEY,
  applyTheme,
  getStoredTheme,
} from './theme'

beforeEach(() => {
  window.localStorage.clear()
  document.documentElement.dataset.theme = 'imsf-swiss'
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('getStoredTheme', () => {
  it('defaults to light when nothing is stored', () => {
    expect(getStoredTheme()).toBe('light')
  })

  it('returns the stored theme when valid', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    expect(getStoredTheme()).toBe('dark')
  })

  it('falls back to light for an unknown stored value', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'system')
    expect(getStoredTheme()).toBe('light')
  })

  it('falls back to light when storage is unavailable', () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })
    expect(getStoredTheme()).toBe('light')
  })
})

describe('THEME_NAMES + applyTheme', () => {
  it('maps light/dark to the DaisyUI theme names', () => {
    expect(THEME_NAMES.light).toBe('imsf-swiss')
    expect(THEME_NAMES.dark).toBe('imsf-swiss-dark')
  })

  it('applyTheme sets data-theme on <html>', () => {
    applyTheme('dark')
    expect(document.documentElement.dataset.theme).toBe('imsf-swiss-dark')
    applyTheme('light')
    expect(document.documentElement.dataset.theme).toBe('imsf-swiss')
  })
})
