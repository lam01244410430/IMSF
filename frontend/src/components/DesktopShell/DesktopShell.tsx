/**
 * DesktopShell — FE-04 desktop web shell (design doc §12.2).
 *
 * Mounted once in src/app.tsx, wrapping {children}. On desktop (H5,
 * >=1024px, except the login route) it renders a fixed sidebar + fixed
 * topbar + left-aligned content wrapper around the page. Everywhere else
 * (H5 <1024px, weapp, login route) it renders {children} only — mobile
 * changes not one pixel.
 *
 * Only Taro primitives (View/Text) + tokens + existing primitives (Button)
 * — NO MUI, NO window, NO matchMedia — so it compiles on weapp as dead
 * code (useIsDesktop() is always false there).
 *
 * Notes (deviations from the brief, all forced by the codebase):
 * - Nav items are label-only: the Icon primitive has no home / fridge /
 *   recipes / mine / edit / list keys (its keys are camera, chevron-*,
 *   check, clock, close, error, image, plus, refresh, search, warning,
 *   info), and the brief says to use no icon rather than invent a key.
 * - Topbar "user name": AuthUser carries no display name (only id +
 *   wechat_openid), so the topbar shows wechat_openid when present, else
 *   the user id, else no name text — just the 退出登录 button.
 * - Content wrapper: marginLeft = sidebarWidth (clears the sidebar) and
 *   no auto margins (left-aligned, not centered) — the "margin: 0" in
 *   §12.2 means no centering, not marginLeft 0.
 */
import type { PropsWithChildren } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useQuery } from '@tanstack/react-query'
import Button from '../../ui/primitives/Button'
import { useIsDesktop } from '../../hooks/useIsDesktop'
import { useSessionStore } from '../../store/session'
import { useUiStore } from '../../store/ui'
import { listHouseholds } from '../../services/households'
import { logout } from '../../services/auth'
import { goLogin, goSpending, goTransactions, routes } from '../../config/routes'
import { resolveCurrency } from '../../utils/format'
import { tokens } from '../../ui/tokens'

interface NavItem {
  label: string
  path: string
  go: () => Promise<unknown>
}

const NAV_ITEMS: NavItem[] = [
  { label: '首页', path: routes.upload, go: () => Taro.switchTab({ url: routes.upload }) },
  { label: '冰箱', path: routes.fridge, go: () => Taro.switchTab({ url: routes.fridge }) },
  { label: '菜谱', path: routes.recipes, go: () => Taro.switchTab({ url: routes.recipes }) },
  { label: '我的', path: routes.mine, go: () => Taro.switchTab({ url: routes.mine }) },
]

const LEDGER_ITEMS: NavItem[] = [
  { label: '记账', path: routes.transactions, go: () => goTransactions() },
  { label: '消费统计', path: routes.spending, go: () => goSpending() },
]

/** Route -> sidebar label (§12.2); any other route highlights nothing. */
const ACTIVE_BY_PATH: Record<string, string> = {
  [routes.upload]: '首页',
  [routes.fridge]: '冰箱',
  [routes.recipes]: '菜谱',
  [routes.mine]: '我的',
  [routes.transactions]: '记账',
  [routes.spending]: '消费统计',
}

function SidebarNavItem({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <View
      onClick={onClick}
      style={{
        position: 'relative',
        height: 48,
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        paddingLeft: 24,
        paddingRight: 16,
        backgroundColor: active ? tokens.action.hover : tokens.color.surface,
      }}
    >
      {active ? (
        <View
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: 3,
            backgroundColor: tokens.color.accent,
          }}
        />
      ) : null}
      <Text
        style={{
          fontSize: 14,
          color: active ? tokens.color.accent : tokens.color.onSurface,
        }}
      >
        {label}
      </Text>
    </View>
  )
}

export default function DesktopShell({ children }: PropsWithChildren) {
  const isDesktop = useIsDesktop()
  const router = useRouter()
  const session = useSessionStore()
  // Same queryKey as the transactions/spending/mine pages — shared cache,
  // no extra request (§12.2).
  const householdsQuery = useQuery({
    queryKey: ['households'],
    queryFn: () => listHouseholds(),
    enabled: session.isLoggedIn,
  })

  const path = router.path ?? ''
  if (!isDesktop || path === routes.login) return <>{children}</>

  const households = householdsQuery.data ?? []
  const current = households.find((h) => h.id === session.currentHouseholdId)
  const householdName = current?.name ?? session.households[0]?.name ?? '—'
  const currency = current ? resolveCurrency(current.default_currency) : 'CNY'
  const timezone = current?.timezone ?? 'Asia/Shanghai'
  const footerName = current?.name ?? session.households[0]?.name ?? null
  const activeLabel = ACTIVE_BY_PATH[path]
  // AuthUser has no display name — show wechat_openid, else id, else nothing.
  const userLabel = session.user?.wechat_openid ?? session.user?.id ?? ''

  const handleCamera = () => {
    // Same behaviour as the mobile FAB (AppTabBar): open the camera when
    // the upload page shows, then switch to it.
    useUiStore.getState().setOpenCameraOnShow(true)
    void Taro.switchTab({ url: routes.upload })
  }

  const handleLogout = () => {
    // Same flow as the 我的 page: clear tokens + session, then login.
    logout()
    session.clearSession()
    void goLogin()
  }

  return (
    <>
      {/* Sidebar — fixed left, hairline on its right edge. */}
      <View
        style={{
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          width: tokens.desktop.sidebarWidth,
          backgroundColor: tokens.color.surface,
          zIndex: tokens.zIndex.drawer,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <View
          style={{
            position: 'absolute',
            right: 0,
            top: 0,
            bottom: 0,
            width: 1,
            backgroundColor: tokens.color.divider,
          }}
        />
        <View
          style={{
            height: tokens.desktop.topbarHeight,
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'center',
            paddingLeft: 24,
          }}
        >
          <Text style={{ fontSize: 20, fontWeight: 700, color: tokens.color.onSurface }}>IMSF-v2</Text>
        </View>
        {NAV_ITEMS.map((item) => (
          <SidebarNavItem
            key={item.label}
            label={item.label}
            active={activeLabel === item.label}
            onClick={() => void item.go()}
          />
        ))}
        <View style={{ height: 1, backgroundColor: tokens.color.divider }} />
        {LEDGER_ITEMS.map((item) => (
          <SidebarNavItem
            key={item.label}
            label={item.label}
            active={activeLabel === item.label}
            onClick={() => void item.go()}
          />
        ))}
        <View style={{ margin: 16 }}>
          <Button variant='primary' block onClick={handleCamera}>
            拍照
          </Button>
        </View>
        <View style={{ flex: 1 }} />
        {footerName ? (
          <View style={{ paddingLeft: 24, paddingRight: 16, paddingTop: 16, paddingBottom: 16 }}>
            <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>{footerName}</Text>
          </View>
        ) : null}
      </View>
      {/* Topbar — fixed top, right of the sidebar, hairline underneath. */}
      <View
        style={{
          position: 'fixed',
          left: tokens.desktop.sidebarWidth,
          right: 0,
          top: 0,
          height: tokens.desktop.topbarHeight,
          backgroundColor: tokens.color.surface,
          zIndex: tokens.zIndex.bottomNavigation,
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingLeft: 24,
          paddingRight: 24,
        }}
      >
        <View
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: 1,
            backgroundColor: tokens.color.divider,
          }}
        />
        <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center' }}>
          <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>{householdName}</Text>
          <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>
            {` · ${currency} · ${timezone}`}
          </Text>
        </View>
        {!session.isLoggedIn ? (
          <Button variant='primary' onClick={() => void goLogin()}>
            去登录
          </Button>
        ) : (
          <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            {userLabel ? (
              <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>{userLabel}</Text>
            ) : null}
            <Button variant='ghost' onClick={handleLogout}>
              退出登录
            </Button>
          </View>
        )}
      </View>
      {/* Content — clears sidebar + topbar, max-width 1200px, LEFT-aligned. */}
      <View
        style={{
          marginLeft: tokens.desktop.sidebarWidth,
          paddingTop: tokens.desktop.topbarHeight,
          maxWidth: tokens.desktop.contentMaxWidth,
        }}
      >
        {children}
      </View>
    </>
  )
}
