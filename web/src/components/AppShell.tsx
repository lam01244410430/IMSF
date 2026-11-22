import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getStoredHouseholdName } from '../lib/auth'
import { Icon, type IconName } from './Icon'
import { AccountMenu } from './AccountMenu'
import { NotificationsBell } from './NotificationsBell'
import { ThemeToggle } from './ThemeToggle'
import logoMarkUrl from '../assets/logo-mark.svg'

interface NavItemDef {
  to: string
  label: string
  icon: IconName
  end?: boolean
}

const NAV_GROUP_1: NavItemDef[] = [
  // 仪表盘 is the first item (Dashboard Phase B, D1): /app redirects
  // to /app/dashboard. The 'home' icon moves here from the old 首页
  // item. There is NO 首页 nav item and NO duplicate 拍照 nav item —
  // /app/upload stays reachable via the sidebar 拍照 button below +
  // the mobile FAB (plan §3.2).
  { to: '/app/dashboard', label: '仪表盘', icon: 'home', end: true },
  { to: '/app/fridge', label: '冰箱', icon: 'fridge' },
  { to: '/blog', label: '菜谱', icon: 'recipes' },
  { to: '/app/mine', label: '我的', icon: 'mine' },
]

const NAV_GROUP_2: NavItemDef[] = [
  { to: '/app/transactions', label: '记账', icon: 'edit' },
  { to: '/app/spending', label: '消费统计', icon: 'list' },
]

function SidebarNavGroup({
  items,
  label,
}: {
  items: NavItemDef[]
  label: string
}) {
  return (
    <nav className="app-sidebar-nav-group" aria-label={label}>
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
 * Topbar account control is the AccountMenu button (icon + display
 * name on desktop, icon-only below 768px) with a dropdown for the
 * account info, a link to /app/mine and logout — the name was plain
 * text and logout lived only on /app/mine before (Lam 2026-11-22).
 */
export function AppShell() {
  const navigate = useNavigate()
  const householdName = getStoredHouseholdName()

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar-brand">
          <Link
            to="/app"
            style={{
              color: 'inherit',
              textDecoration: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <img
              src={logoMarkUrl}
              alt=""
              className="app-sidebar-brand-mark"
            />
            IMSF
          </Link>
        </div>
        <SidebarNavGroup items={NAV_GROUP_1} label="应用导航" />
        <SidebarNavGroup items={NAV_GROUP_2} label="记账导航" />
        <button
          type="button"
          className="app-sidebar-photo"
          onClick={() => navigate('/app/upload')}
        >
          拍照
        </button>
        <div className="app-sidebar-footer">
          {householdName ? `家庭 ${householdName}` : '家庭'}
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <span className="app-topbar-item">家庭</span>
          <span className="app-topbar-item">CNY</span>
          <span className="app-topbar-item">Asia/Shanghai</span>
          <span className="app-topbar-spacer" />
          <ThemeToggle />
          <NotificationsBell />
          <AccountMenu />
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
