/**
 * Language dropdown tests (Dashboard Phase A, D4): open/close,
 * keyboard navigation (ArrowUp/Down, Home/End), Enter/Space select +
 * persist localStorage['imsf.lang'], Escape closes + focus returns
 * to the trigger, click-outside closes, aria-expanded / aria-checked
 * are correct, exactly 3 options with short codes.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { LanguageSwitcher } from './LanguageSwitcher'
import { LanguageProvider } from '../lib/LanguageProvider'
import { LANGUAGE_STORAGE_KEY, useLanguage } from '../lib/i18n'

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  window.localStorage.clear()
})

function Probe() {
  const { t } = useLanguage()
  return (
    <>
      <LanguageSwitcher />
      <p>{t['hero.title']}</p>
    </>
  )
}

function renderSwitcher() {
  return render(
    <LanguageProvider>
      <Probe />
    </LanguageProvider>,
  )
}

function trigger() {
  // The trigger's accessible name follows the current language
  // ('语言' / 'Ngôn ngữ' / 'Language'), so match by role + any
  // of the three names.
  return screen.getByRole('button', { name: /语言|Ngôn ngữ|Language/ })
}

function openPanel() {
  fireEvent.click(trigger())
  return screen.getByRole('menu')
}

describe('LanguageSwitcher dropdown', () => {
  it('shows the current language short code and starts closed', () => {
    renderSwitcher()
    expect(trigger().textContent).toContain('中文')
    expect(trigger().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('opens a 3-option panel with names, short codes and a tick on the current language', () => {
    renderSwitcher()
    const panel = openPanel()
    // The open menu is named (spec §5.2) with a label DISTINCT from
    // the trigger's ('语言'), so getByLabelText('语言') still matches
    // exactly one element.
    expect(panel.getAttribute('aria-label')).toBe('选择语言')
    expect(trigger().getAttribute('aria-expanded')).toBe('true')
    const options = screen.getAllByRole('menuitemradio')
    expect(options).toHaveLength(3)
    expect(options[0]?.getAttribute('aria-checked')).toBe('true')
    expect(options[1]?.getAttribute('aria-checked')).toBe('false')
    expect(screen.getByText('English')).toBeTruthy()
    expect(screen.getByText('EN')).toBeTruthy()
    expect(screen.getByText('VI')).toBeTruthy()
  })

  it('clicking an option switches the language, persists it, closes the panel and returns focus', () => {
    renderSwitcher()
    openPanel()
    fireEvent.click(screen.getByRole('menuitemradio', { name: /English/ }))
    expect(
      screen.getByText('Snap one receipt — your fridge and ledger are done.'),
    ).toBeTruthy()
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(document.activeElement).toBe(trigger())
  })

  it('ArrowDown opens the panel and focuses the selected option, then moves down and wraps', () => {
    renderSwitcher()
    trigger().focus()
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' })
    const options = screen.getAllByRole('menuitemradio')
    expect(document.activeElement).toBe(options[0])
    fireEvent.keyDown(options[0] as HTMLElement, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(options[1])
    fireEvent.keyDown(options[1] as HTMLElement, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(options[2])
    fireEvent.keyDown(options[2] as HTMLElement, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(options[0])
  })

  it('ArrowUp moves up, Home jumps to first, End jumps to last', () => {
    renderSwitcher()
    openPanel()
    const options = screen.getAllByRole('menuitemradio')
    fireEvent.keyDown(options[0] as HTMLElement, { key: 'End' })
    expect(document.activeElement).toBe(options[2])
    fireEvent.keyDown(options[2] as HTMLElement, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(options[1])
    fireEvent.keyDown(options[1] as HTMLElement, { key: 'Home' })
    expect(document.activeElement).toBe(options[0])
  })

  it('Enter on an option selects it', () => {
    renderSwitcher()
    trigger().focus()
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' })
    const options = screen.getAllByRole('menuitemradio')
    fireEvent.keyDown(options[2] as HTMLElement, { key: 'ArrowDown' })
    fireEvent.keyDown(options[2] as HTMLElement, { key: 'ArrowDown' })
    fireEvent.keyDown(document.activeElement as HTMLElement, {
      key: 'Enter',
    })
    expect(
      screen.getByText('Snap one receipt — your fridge and ledger are done.'),
    ).toBeTruthy()
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en')
  })

  it('Escape closes the panel and returns focus to the trigger', () => {
    renderSwitcher()
    openPanel()
    const options = screen.getAllByRole('menuitemradio')
    fireEvent.keyDown(options[0] as HTMLElement, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    expect(document.activeElement).toBe(trigger())
  })

  it('clicking outside closes the panel', () => {
    renderSwitcher()
    openPanel()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
  })
})
