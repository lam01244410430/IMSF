/**
 * ThemeToggle tests (Dashboard Phase A, D2): the toggle flips the
 * theme, writes localStorage['imsf.theme'], sets data-theme on
 * <html>, and its aria-label names the action. A stored choice
 * survives a remount (the provider reads it on init).
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ThemeToggle } from './ThemeToggle'
import { ThemeProvider } from '../lib/ThemeProvider'
import { LanguageProvider } from '../lib/LanguageProvider'
import { THEME_STORAGE_KEY } from '../lib/theme'

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  window.localStorage.clear()
  document.documentElement.dataset.theme = 'imsf-swiss'
})

function renderToggle() {
  return render(
    <LanguageProvider>
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    </LanguageProvider>,
  )
}

describe('ThemeToggle', () => {
  it('shows the switch-to-dark action in light mode and flips to dark on click', () => {
    renderToggle()
    const button = screen.getByRole('button', {
      name: '切换到深色模式',
    })
    fireEvent.click(button)
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('imsf-swiss-dark')
    expect(
      screen.getByRole('button', { name: '切换到浅色模式' }),
    ).toBeTruthy()
  })

  it('flips back to light on a second click', () => {
    renderToggle()
    fireEvent.click(screen.getByRole('button', { name: '切换到深色模式' }))
    fireEvent.click(screen.getByRole('button', { name: '切换到浅色模式' }))
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('imsf-swiss')
  })

  it('starts dark when a dark choice is stored', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    renderToggle()
    expect(
      screen.getByRole('button', { name: '切换到浅色模式' }),
    ).toBeTruthy()
    expect(document.documentElement.dataset.theme).toBe('imsf-swiss-dark')
  })
})
