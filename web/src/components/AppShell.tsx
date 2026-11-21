import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getAccessToken, getStoredHouseholdId } from '../lib/auth'
import { Icon, type IconName } from './Icon'
import { NotificationsBell } from './NotificationsBell'

interface NavItemDef {
  to: string
  label: string
  icon: IconName
  end?: boolean
}

const NAV_GROUP_1: NavItemDef[] = [
  // 首页 points to /app/upload: /app itself redirects there (plan §3.2 Q2).
  { to: '/app/upload', label: '首页', icon: 'home', end: true },
  { to: '/app/fridge', label: '冰箱', icon: 'fridge' },
  { to: '/blog', label: '菜谱', icon: 'recipes' },
  { to: '/app/mine', label: '我的', icon: 'mine' },
]

const NAV_GROUP_2: NavItemDef[] = [
  { to: '/app/transactions', label: '记账', icon: 'edit' },
  { to: '/app/spending', label: '消费统计', icon: 'list' },
]

function SidebarNavGroup({ items }: { items: NavItemDef[] }) {
  return (
    <nav className="app-sidebar-nav-group" aria-label="应用导航">
      <div className="app-sidebar-nav">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `sidebar-nav-item${isActive ? ' active' : ''}`
            }
          >
            <Icon name={item.icon} className="nav-icon" />
            <span className="nav-label">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

/**
 * App shell (FE-04 layout, plain CSS): sidebar 240px + topbar 64px +
 * content max-width 1200px left-aligned (desktop ≥1024px); below
 * 1024px the mobile bottom-nav layout (bottom nav + centre FAB, no
 * sidebar). Sidebar hover follows the EXACT §5.1 spec in index.css.
 *
 * Topbar shows the user id for now — no display name exists in the
 * backend yet (recorded FE-04 caveat).
 */
export function AppShell() {
  const navigate = useNavigate()
  const householdId = getStoredHouseholdId()
  const userId = getUserIdFromToken()

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar-brand">
          <Link
            to="/app"
            style={{ color: 'inherit', textDecoration: 'none' }}
          >
            IMSF
          </Link>
        </div>
        <SidebarNavGroup items={NAV_GROUP_1} />
        <SidebarNavGroup items={NAV_GROUP_2} />
        <button
          type="button"
          className="app-sidebar-photo"
          onClick={() => navigate('/app/upload')}
        >
          拍照
        </button>
        <div className="app-sidebar-footer">
          {householdId ? `家庭 ${householdId}` : '家庭'}
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <span className="app-topbar-item">家庭</span>
          <span className="app-topbar-item">CNY</span>
          <span className="app-topbar-item">Asia/Shanghai</span>
          <span className="app-topbar-spacer" />
          <NotificationsBell />
          <span className="app-topbar-user">
            {userId ? `用户 ${userId}` : '未登录'}
          </span>
        </header>
        <main className="app-content">
          <Outlet />
        </main>
      </div>

      <nav className="app-bottomnav" aria-label="应用导航">
        {[...NAV_GROUP_1].map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `app-bottomnav-item${isActive ? ' active' : ''}`
            }
          >
            <Icon name={item.icon} className="nav-icon" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <button
        type="button"
        className="app-fab"
        aria-label="拍照"
        onClick={() => navigate('/app/upload')}
      >
        +
      </button>
    </div>
  )
}

function getUserIdFromToken(): string | null {
  const token = getAccessToken()
  if (!token) return null
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const json = JSON.parse(
      globalThis.atob(
        payload.replace(/-/g, '+').replace(/_/g, '/') +
          '='.repeat((4 - (payload.length % 4)) % 4),
      ),
    ) as { sub?: string }
    return typeof json.sub === 'string' ? json.sub : null
  } catch {
    return null
  }
}
