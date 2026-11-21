/**
 * i18n unit tests: default language, persistence, switching, and the
 * `{placeholder}` fill helper.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import {
  LANGUAGE_STORAGE_KEY,
  fill,
  getStoredLanguage,
  useLanguage,
} from './i18n'
import { LanguageProvider } from './LanguageProvider'
import { LanguageSwitcher } from '../components/LanguageSwitcher'

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

describe('getStoredLanguage', () => {
  it('defaults to zh-CN when nothing is stored', () => {
    expect(getStoredLanguage()).toBe('zh-CN')
  })

  it('returns the stored language when valid', () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'vi')
    expect(getStoredLanguage()).toBe('vi')
  })

  it('falls back to zh-CN for an unknown stored value', () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'fr')
    expect(getStoredLanguage()).toBe('zh-CN')
  })
})

describe('LanguageProvider', () => {
  it('renders zh-CN copy by default', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    expect(
      screen.getByText('拍一张小票，冰箱和账本都记好了。'),
    ).toBeTruthy()
  })

  it('switching the language re-renders the same content in English and persists the choice', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    fireEvent.click(screen.getByLabelText('语言'))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /English/ }))
    expect(
      screen.getByText('Snap one receipt — your fridge and ledger are done.'),
    ).toBeTruthy()
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en')
  })

  it('switching to Vietnamese renders Vietnamese copy', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    fireEvent.click(screen.getByLabelText('语言'))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /Tiếng Việt/ }))
    expect(
      screen.getByText(
        'Chụp một tờ hoá đơn, tủ lạnh và sổ chi tiêu đều đã ghi xong.',
      ),
    ).toBeTruthy()
  })
})

describe('fill', () => {
  it('replaces {mm} and {ss} placeholders', () => {
    expect(fill('已锁定，{mm}:{ss} 后可重试', { mm: '14', ss: '59' })).toBe(
      '已锁定，14:59 后可重试',
    )
  })

  it('leaves a template without placeholders unchanged', () => {
    expect(fill('没有占位符', { mm: '00' })).toBe('没有占位符')
  })
})
