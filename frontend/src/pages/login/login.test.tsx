/**
 * Login page tests (Step 4, §8.4): WeChat login thành công → switchTab
 * upload; Taro.login thất bại (H5) → hiện「请在微信中打开小程序登录」.
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { taroMock, __resetTaroStorage } from '../../test/taroMock'
import Login from './index'
import { useSessionStore } from '../../store/session'

beforeEach(() => {
  vi.clearAllMocks()
  __resetTaroStorage()
  useSessionStore.getState().clearSession()
})

afterEach(() => {
  cleanup()
})

describe('Login page', () => {
  it('logs in with WeChat and switches to upload', async () => {
    vi.mocked(taroMock.login).mockResolvedValue({ code: 'code-1' })
    vi.mocked(taroMock.request).mockResolvedValue({
      statusCode: 200,
      data: {
        access_token: 'access-1',
        refresh_token: 'refresh-1',
        user: { id: 'u-1', wechat_openid: 'o-1' },
        households: [{ id: 'hh-1', name: '家' }],
      },
    })
    render(<Login />)
    fireEvent.click(screen.getByRole('button', { name: '微信登录' }))
    await waitFor(() => {
      expect(taroMock.switchTab).toHaveBeenCalledWith({ url: '/pages/upload/index' })
    })
    expect(useSessionStore.getState().isLoggedIn).toBe(true)
  })

  it('shows the H5 hint when Taro.login fails', async () => {
    vi.mocked(taroMock.login).mockRejectedValue(new Error('login not available'))
    render(<Login />)
    fireEvent.click(screen.getByRole('button', { name: '微信登录' }))
    expect(await screen.findByText('请在微信中打开小程序登录')).toBeTruthy()
    expect(taroMock.switchTab).not.toHaveBeenCalled()
  })
})
