/**
 * DesktopShell test (FE-04, design doc §12.2/§12.8): children-only on mobile
 * and on the login route; sidebar (6 nav labels + 拍照) + topbar on desktop.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import DesktopShell from './DesktopShell'
import { taroMock, __resetTaroStorage } from '../../test/taroMock'
import { useSessionStore } from '../../store/session'
import { useUiStore } from '../../store/ui'
import { routes } from '../../config/routes'
import { STORAGE_KEYS } from '../../services/auth'

vi.mock('../../services/households', () => ({
  listHouseholds: vi.fn(() =>
    Promise.resolve([
      {
        id: 'h-1',
        name: '家',
        default_currency: 'CNY',
        timezone: 'Asia/Shanghai',
        locale: 'zh-CN',
        created_at: null,
        role: 'owner',
      },
    ]),
  ),
}))

/** Controllable window.matchMedia (same shape as the setup.ts default). */
function mockMatchMedia(initialMatches: boolean): void {
  const createMql = () => ({
    matches: initialMatches,
    media: '(min-width: 1024px)',
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
  window.matchMedia = vi.fn(createMql) as unknown as typeof window.matchMedia
}

function setRoute(path: string | undefined) {
  ;(
    taroMock.useRouter as unknown as { mockReturnValue: (value: unknown) => void }
  ).mockReturnValue({ path, params: {} })
}

function loginAs() {
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-valid')
  useSessionStore.setState({
    user: { id: 'u-1', wechat_openid: 'openid-1' },
    households: [{ id: 'h-1', name: '家' }],
    currentHouseholdId: 'h-1',
    isLoggedIn: true,
  })
}

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(
    <DesktopShell>
      <div>页面内容</div>
    </DesktopShell>,
    { wrapper },
  )
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  setRoute(undefined)
  useSessionStore.setState({ user: null, households: [], currentHouseholdId: null, isLoggedIn: false })
  useUiStore.setState({ openCameraOnShow: false })
  mockMatchMedia(false)
})

afterEach(() => {
  cleanup()
  window.matchMedia = originalMatchMedia
})

describe('DesktopShell', () => {
  it('renders children only when not desktop', () => {
    mockMatchMedia(false)
    setRoute(routes.upload)
    loginAs()
    renderShell()
    expect(screen.getByText('页面内容')).toBeTruthy()
    expect(screen.queryByText('首页')).toBeNull()
    expect(screen.queryByText('记账')).toBeNull()
    expect(screen.queryByText('消费统计')).toBeNull()
    expect(screen.queryByText('拍照')).toBeNull()
  })

  it('renders sidebar + topbar on desktop when logged in', async () => {
    mockMatchMedia(true)
    setRoute(routes.upload)
    loginAs()
    renderShell()
    expect(screen.getByText('页面内容')).toBeTruthy()
    // Sidebar: brand + all 6 nav labels + 拍照 button.
    expect(screen.getByText('IMSF-v2')).toBeTruthy()
    for (const label of ['首页', '冰箱', '菜谱', '我的', '记账', '消费统计']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    expect(screen.getByText('拍照')).toBeTruthy()
    // Active item (upload route -> 首页) renders in the accent colour.
    expect(screen.getByText('首页').style.color).toBe('rgb(194, 65, 12)')
    expect(screen.getByText('冰箱').style.color).toBe('rgb(26, 28, 26)')
    // Topbar: household name (topbar + sidebar footer) + currency/timezone.
    expect(await screen.findAllByText('家')).toHaveLength(2)
    expect(screen.getByText('CNY · Asia/Shanghai', { exact: false })).toBeTruthy()
    // Topbar right: user label + 退出登录.
    expect(screen.getByText('openid-1')).toBeTruthy()
    expect(screen.getByText('退出登录')).toBeTruthy()
  })

  it('shows 去登录 on desktop when logged out', () => {
    mockMatchMedia(true)
    setRoute(routes.upload)
    renderShell()
    expect(screen.getByText('去登录')).toBeTruthy()
    expect(screen.queryByText('退出登录')).toBeNull()
    expect(screen.queryByText('家')).toBeNull()
  })

  it('renders children only on the login route even on desktop', () => {
    mockMatchMedia(true)
    setRoute(routes.login)
    loginAs()
    renderShell()
    expect(screen.getByText('页面内容')).toBeTruthy()
    expect(screen.queryByText('首页')).toBeNull()
    expect(screen.queryByText('拍照')).toBeNull()
    expect(screen.queryByText('退出登录')).toBeNull()
  })

  it('navigates from sidebar items and the 拍照 button', () => {
    mockMatchMedia(true)
    setRoute(routes.upload)
    loginAs()
    renderShell()
    fireEvent.click(screen.getByText('冰箱'))
    expect(taroMock.switchTab).toHaveBeenCalledWith({ url: routes.fridge })
    fireEvent.click(screen.getByText('记账'))
    expect(taroMock.navigateTo).toHaveBeenCalledWith({ url: routes.transactions })
    fireEvent.click(screen.getByText('拍照'))
    expect(useUiStore.getState().openCameraOnShow).toBe(true)
    expect(taroMock.switchTab).toHaveBeenCalledWith({ url: routes.upload })
  })

  it('logs out from the topbar like the 我的 page', () => {
    mockMatchMedia(true)
    setRoute(routes.upload)
    loginAs()
    renderShell()
    fireEvent.click(screen.getByText('退出登录'))
    expect(useSessionStore.getState().isLoggedIn).toBe(false)
    expect(taroMock.redirectTo).toHaveBeenCalledWith({ url: routes.login })
  })
})
