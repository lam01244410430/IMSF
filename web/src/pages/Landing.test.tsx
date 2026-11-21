/**
 * Landing page tests (reform plan §4): sections render, FAQ accordion
 * behaviour + aria, honest empty review slots, language switching.
 *
 * NOTE: this project has no jest-dom matchers, so assertions use plain
 * vitest (`getAttribute`, `textContent`, `disabled`) instead of
 * `toHaveAttribute` / `toHaveTextContent` / `toBeDisabled`.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { LandingPage } from './Landing'
import { LanguageProvider } from '../lib/LanguageProvider'

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  window.localStorage.clear()
})

function renderLanding(ui: ReactElement = <LandingPage />) {
  return render(
    <LanguageProvider>
      <MemoryRouter initialEntries={['/']}>{ui}</MemoryRouter>
    </LanguageProvider>,
  )
}

function hrefOf(el: HTMLElement | null): string | null {
  return el?.getAttribute('href') ?? null
}

describe('header', () => {
  it('shows the four menu items with the right targets', () => {
    renderLanding()
    const header = document.querySelector('.landing-header') as HTMLElement
    expect(
      hrefOf(within(header).getByRole('link', { name: '功能' })),
    ).toBe('#features')
    expect(
      hrefOf(within(header).getByRole('link', { name: '使用方法' })),
    ).toBe('#how-it-works')
    expect(
      hrefOf(within(header).getByRole('link', { name: '菜谱' })),
    ).toBe('/blog')
    expect(
      hrefOf(within(header).getByRole('link', { name: '常见问题' })),
    ).toBe('#faq')
  })

  it('shows 登录 / 注册 when logged out', () => {
    renderLanding()
    const header = document.querySelector('.landing-header') as HTMLElement
    expect(hrefOf(within(header).getByRole('link', { name: '登录' }))).toBe(
      '/login',
    )
    expect(hrefOf(within(header).getByRole('link', { name: '注册' }))).toBe(
      '/register',
    )
  })

  it('shows the user name + 进入应用 instead of 登录 / 注册 when logged in', () => {
    window.localStorage.setItem('imsf2.access_token', 'token')
    window.localStorage.setItem('imsf2.user_name', '小明')
    renderLanding()
    const header = document.querySelector('.landing-header') as HTMLElement
    expect(within(header).getByText('小明')).toBeTruthy()
    expect(
      hrefOf(within(header).getByRole('link', { name: '进入应用' })),
    ).toBe('/app')
    expect(within(header).queryByRole('link', { name: '登录' })).toBeNull()
    expect(within(header).queryByRole('link', { name: '注册' })).toBeNull()
  })
})

describe('hero + trust', () => {
  it('renders the hero headline, sub-headline and three value props', () => {
    renderLanding()
    expect(
      screen.getByRole('heading', {
        name: '拍一张小票，冰箱和账本都记好了。',
      }),
    ).toBeTruthy()
    expect(
      screen.getByText(
        'IMSF 帮一家人管好冰箱、记好每一笔支出，快过期的食材还会推荐菜谱。',
      ),
    ).toBeTruthy()
    expect(screen.getByText('拍照自动入库记账')).toBeTruthy()
    expect(screen.getByText('快过期，推荐菜谱')).toBeTruthy()
    expect(screen.getByText('一家人，共用一本账')).toBeTruthy()
    const ctas = screen.getAllByRole('link', { name: '开始免费使用' })
    expect(ctas).toHaveLength(2)
    for (const cta of ctas) {
      expect(hrefOf(cta)).toBe('/register')
    }
  })

  it('uses an honest mock frame for the hero visual, not a fake screenshot', () => {
    renderLanding()
    expect(screen.getByText('应用预览')).toBeTruthy()
    // The mock label also appears on the five feature mocks.
    expect(screen.getAllByText('界面预览（示意）').length).toBeGreaterThan(0)
    expect(screen.queryByRole('img', { name: /截图|照片/ })).toBeNull()
  })

  it('renders the three trust columns', () => {
    renderLanding()
    expect(screen.getByText('为家庭而做')).toBeTruthy()
    expect(screen.getByText('没有广告')).toBeTruthy()
    expect(screen.getByText('你的数据属于你')).toBeTruthy()
  })
})

describe('features + how-it-works', () => {
  it('renders all five feature blocks with honest mock slots', () => {
    renderLanding()
    for (const title of [
      '智能识别小票',
      '智能冰箱',
      '家庭账本',
      '社区菜谱',
      '设备保养',
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeTruthy()
    }
    // 5 feature mocks + the hero mock caption.
    expect(screen.getAllByText('界面预览（示意）')).toHaveLength(6)
    expect(
      hrefOf(screen.getByRole('link', { name: '去看看菜谱 →' })),
    ).toBe('/blog')
  })

  it('renders the three steps', () => {
    renderLanding()
    expect(screen.getByRole('heading', { name: '使用方法' })).toBeTruthy()
    expect(screen.getByText('拍小票')).toBeTruthy()
    expect(screen.getByText('自动入库记账')).toBeTruthy()
    expect(screen.getByText('快过期，做道菜')).toBeTruthy()
  })

  it('shows the video demo slot with no fake play button', () => {
    renderLanding()
    expect(screen.getByText('演示视频即将上线')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /播放|play/i })).toBeNull()
  })
})

describe('reviews', () => {
  it('has exactly three empty slots with the honest text — no fake names, quotes or stars', () => {
    renderLanding()
    expect(screen.getByText('大家怎么说')).toBeTruthy()
    expect(
      screen.getAllByText(
        '虚位以待 — 第一批家庭的使用反馈会出现在这里。',
      ),
    ).toHaveLength(3)
    expect(screen.queryByText(/★|☆/)).toBeNull()
  })
})

describe('FAQ accordion', () => {
  it('opens one question at a time, with aria-expanded + aria-controls', () => {
    renderLanding()
    const q1 = screen.getByRole('button', { name: /IMSF 免费吗？/ })
    const q2 = screen.getByRole('button', { name: /支持哪些语言？/ })
    expect(q1.getAttribute('aria-expanded')).toBe('false')
    expect(q1.getAttribute('aria-controls')).toBe('faq-panel-0')
    expect(screen.queryByText(/家庭使用免费/)).toBeNull()

    fireEvent.click(q1)
    expect(q1.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText(/家庭使用免费/)).toBeTruthy()

    fireEvent.click(q2)
    expect(q2.getAttribute('aria-expanded')).toBe('true')
    expect(screen.queryByText(/家庭使用免费/)).toBeNull()
    expect(screen.getByText(/界面支持中文、越南文和英文/)).toBeTruthy()

    fireEvent.click(q2)
    expect(q2.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText(/界面支持中文、越南文和英文/)).toBeNull()
  })

  it('answers the login question with the post-reform answer (web = email, Mini Program = WeChat)', () => {
    renderLanding()
    fireEvent.click(screen.getByRole('button', { name: /怎么登录？/ }))
    expect(
      screen.getByText('网页版用邮箱登录，微信小程序里用微信登录。'),
    ).toBeTruthy()
  })
})

describe('language switching', () => {
  it('switching to English changes the landing copy on the same route', () => {
    renderLanding()
    const selects = screen.getAllByLabelText('语言')
    fireEvent.change(selects[0], { target: { value: 'en' } })
    expect(
      screen.getByRole('heading', {
        name: 'Snap one receipt — your fridge and ledger are done.',
      }),
    ).toBeTruthy()
    expect(screen.getByText('What families say')).toBeTruthy()
    expect(
      screen.getAllByText(
        'Awaiting real feedback — the first families’ reviews will appear here.',
      ),
    ).toHaveLength(3)
    expect(window.localStorage.getItem('imsf.lang')).toBe('en')
  })

  it('switching to Vietnamese changes the landing copy', () => {
    renderLanding()
    const selects = screen.getAllByLabelText('语言')
    fireEvent.change(selects[0], { target: { value: 'vi' } })
    expect(
      screen.getByText(
        'Chụp một tờ hoá đơn, tủ lạnh và sổ chi tiêu đều đã ghi xong.',
      ),
    ).toBeTruthy()
    expect(screen.getByText('Mọi người nói gì')).toBeTruthy()
  })
})
