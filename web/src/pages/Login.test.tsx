/**
 * Login page tests (reform plan §7.8): frontend validation, the exact
 * error mapping, 401 keeps the email + clears the password, 429 locks
 * the form, and there is no WeChat button on web.
 *
 * NOTE: this project has no jest-dom matchers, so assertions use plain
 * vitest (`textContent`, `disabled`, `getAttribute`) instead of
 * `toHaveTextContent` / `toBeDisabled` / `toHaveAttribute`.
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
import { LoginPage } from './Login'
import { LanguageProvider } from '../lib/LanguageProvider'

// The mocked auth module: loginWithEmail is a spy, and ApiError is a local
// class so `instanceof` works on both sides of the mock. Both must be
// created with vi.hoisted: the vi.mock factory runs before the module
// body, so plain top-level consts are still in their TDZ there.
const { mockLogin, mockApiError } = vi.hoisted(() => {
  class MockApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  }
  return { mockLogin: vi.fn(), mockApiError: MockApiError }
})
vi.mock('../lib/auth', () => ({
  loginWithEmail: mockLogin,
  ApiError: mockApiError,
}))

// Re-import through the mock so tests throw the same ApiError class.
import { ApiError, loginWithEmail } from '../lib/auth'

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

function renderLogin(ui: ReactElement = <LoginPage />) {
  return render(
    <LanguageProvider>
      <MemoryRouter initialEntries={['/login']}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </LanguageProvider>,
  )
}

function fillForm(email: string, password: string) {
  fireEvent.change(screen.getByLabelText('邮箱'), {
    target: { value: email },
  })
  fireEvent.change(screen.getByLabelText('密码'), {
    target: { value: password },
  })
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: '登录' }))
}

function alertText(): string {
  return screen.getByRole('alert').textContent ?? ''
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: '登录' }) as HTMLButtonElement
}

describe('validation', () => {
  it('rejects an invalid email before any API call', () => {
    renderLogin()
    fillForm('not-an-email', 'longenough')
    submit()
    expect(screen.getByText('请输入有效的邮箱地址')).toBeTruthy()
    expect(loginWithEmail).not.toHaveBeenCalled()
  })

  it('rejects a password shorter than 8 chars before any API call', () => {
    renderLogin()
    fillForm('a@b.c', 'short')
    submit()
    expect(screen.getByText('密码至少8位')).toBeTruthy()
    expect(loginWithEmail).not.toHaveBeenCalled()
  })

  it('shows the email-only note and a link to register', () => {
    renderLogin()
    expect(
      screen.getByText('网页端仅支持邮箱登录；微信登录请在小程序中使用。'),
    ).toBeTruthy()
    expect(
      screen
        .getByRole('link', { name: '还没有账号？去注册' })
        .getAttribute('href'),
    ).toBe('/register')
  })

  it('has a show/hide password toggle', () => {
    renderLogin()
    const input = screen.getByLabelText('密码') as HTMLInputElement
    expect(input.type).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: '显示密码' }))
    expect(input.type).toBe('text')
    fireEvent.click(screen.getByRole('button', { name: '隐藏密码' }))
    expect(input.type).toBe('password')
  })

  it('has no WeChat button anywhere on the web login page', () => {
    renderLogin()
    expect(screen.queryByRole('button', { name: /微信/ })).toBeNull()
  })
})

describe('error mapping', () => {
  it('401 shows the exact banner, keeps the email, clears only the password', async () => {
    mockLogin.mockRejectedValueOnce(
      new ApiError(401, 'Invalid email or password'),
    )
    renderLogin()
    fillForm('a@b.c', 'wrongpass')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain('邮箱或密码错误')
    })
    expect(
      (screen.getByLabelText('邮箱') as HTMLInputElement).value,
    ).toBe('a@b.c')
    expect((screen.getByLabelText('密码') as HTMLInputElement).value).toBe(
      '',
    )
  })

  it('429 shows the lock message and disables the submit button', async () => {
    mockLogin.mockRejectedValueOnce(new ApiError(429, 'Too many requests'))
    renderLogin()
    fillForm('a@b.c', 'wrongpass')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain(
        '密码错误次数过多，该账号已被暂时锁定，请15分钟后再试',
      )
    })
    expect(submitButton().disabled).toBe(true)
    expect(screen.getByText(/已锁定，.*后可重试/)).toBeTruthy()
  })

  it('a network failure shows the network banner', async () => {
    mockLogin.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    renderLogin()
    fillForm('a@b.c', 'longenough')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain('网络错误，请检查网络后重试')
    })
  })

  it('a 500 shows the server banner', async () => {
    mockLogin.mockRejectedValueOnce(new ApiError(500, 'boom'))
    renderLogin()
    fillForm('a@b.c', 'longenough')
    submit()
    await waitFor(() => {
      expect(alertText()).toContain('服务暂时不可用，请稍后再试')
    })
  })
})

describe('success', () => {
  it('navigates to /app on success', async () => {
    mockLogin.mockResolvedValueOnce({
      access_token: 'a',
      refresh_token: 'r',
      user: { id: 'u1', email: 'a@b.c' },
      households: [],
    })
    renderLogin()
    fillForm('a@b.c', 'longenough')
    submit()
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/app')
    })
    expect(loginWithEmail).toHaveBeenCalledWith('a@b.c', 'longenough')
  })
})
