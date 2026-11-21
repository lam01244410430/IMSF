/**
 * Register page tests (reform plan §7.8): frontend validation
 * (email, password length, confirm match — the match is checked
 * client-side only), the 409 message with its login link, and no
 * WeChat button on web.
 *
 * NOTE: this project has no jest-dom matchers, so assertions use plain
 * vitest (`textContent`, `getAttribute`) instead of `toHaveTextContent`
 * / `toHaveAttribute`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { RegisterPage } from './Register'
import { LanguageProvider } from '../lib/LanguageProvider'

// The mocked auth module: registerWithEmail is a spy, and ApiError is
// a local class so `instanceof` works on both sides of the mock. Both
// must be created with vi.hoisted: the vi.mock factory runs before the
// module body, so plain top-level consts are still in their TDZ there.
const { mockRegister, mockApiError } = vi.hoisted(() => {
  class MockApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  }
  return { mockRegister: vi.fn(), mockApiError: MockApiError }
})
vi.mock('../lib/auth', () => ({
  registerWithEmail: mockRegister,
  ApiError: mockApiError,
}))

import { ApiError, registerWithEmail } from '../lib/auth'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  window.localStorage.clear()
})

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname}</p>
}

function renderRegister(ui: ReactElement = <RegisterPage />) {
  return render(
    <LanguageProvider>
      <MemoryRouter initialEntries={['/register']}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </LanguageProvider>,
  )
}

function fillForm(
  email: string,
  password: string,
  confirm: string,
  name = '',
) {
  fireEvent.change(screen.getByLabelText('邮箱'), {
    target: { value: email },
  })
  fireEvent.change(screen.getByLabelText('密码'), {
    target: { value: password },
  })
  fireEvent.change(screen.getByLabelText('确认密码'), {
    target: { value: confirm },
  })
  if (name !== '') {
    fireEvent.change(screen.getByLabelText('姓名（可选）'), {
      target: { value: name },
    })
  }
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: '注册' }))
}

function alertText(): string {
  return screen.getByRole('alert').textContent ?? ''
}

describe('validation', () => {
  it('rejects mismatched passwords before any API call', () => {
    renderRegister()
    fillForm('a@b.c', 'longenough', 'different1')
    submit()
    expect(screen.getByText('两次输入的密码不一致')).toBeTruthy()
    expect(registerWithEmail).not.toHaveBeenCalled()
  })

  it('rejects an invalid email and a short password', () => {
    renderRegister()
    fillForm('bad', 'short', 'short')
    submit()
    expect(screen.getByText('请输入有效的邮箱地址')).toBeTruthy()
    expect(screen.getByText('密码至少8位')).toBeTruthy()
    expect(registerWithEmail).not.toHaveBeenCalled()
  })

  it('has no WeChat button anywhere on the web register page', () => {
    renderRegister()
    expect(screen.queryByRole('button', { name: /微信/ })).toBeNull()
  })

  it('links to the login page', () => {
    renderRegister()
    expect(
      screen
        .getByRole('link', { name: '已有账号？去登录' })
        .getAttribute('href'),
    ).toBe('/login')
  })
})

describe('error mapping', () => {
  it('409 shows the exact message with a link to /login', async () => {
    mockRegister.mockRejectedValueOnce(
      new ApiError(409, 'Email already registered'),
    )
    renderRegister()
    fillForm('a@b.c', 'longenough', 'longenough')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain('该邮箱已被注册，请直接登录')
    })
    expect(
      screen
        .getByRole('link', { name: '去登录' })
        .getAttribute('href'),
    ).toBe('/login')
  })

  it('429 shows the rate-limit message', async () => {
    mockRegister.mockRejectedValueOnce(
      new ApiError(429, 'Too many requests'),
    )
    renderRegister()
    fillForm('a@b.c', 'longenough', 'longenough')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain('请求过于频繁，请稍后再试')
    })
  })

  it('a network failure shows the network banner', async () => {
    mockRegister.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    renderRegister()
    fillForm('a@b.c', 'longenough', 'longenough')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain('网络错误，请检查网络后重试')
    })
  })
})

describe('success', () => {
  it('navigates to /app on success and sends the name but never the confirm password', async () => {
    mockRegister.mockResolvedValueOnce({
      access_token: 'a',
      refresh_token: 'r',
      user: { id: 'u1', email: 'a@b.c', name: '小明' },
      households: [],
    })
    renderRegister()
    fillForm('a@b.c', 'longenough', 'longenough', '小明')
    submit()
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/app')
    })
    expect(registerWithEmail).toHaveBeenCalledWith(
      'a@b.c',
      'longenough',
      undefined,
      '小明',
    )
    const body = JSON.stringify(mockRegister.mock.calls[0])
    expect(body).not.toContain('different1')
  })
})
