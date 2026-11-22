/**
 * Mine (/app/mine) — account page. Shows the stored display name
 * (from the login/register response, else the email local part --
 * never the raw user id, Phase 4 F-06) and the email stored at login
 * when available; household info from GET /households; logout
 * button. Links to the receipts list and to equipment maintenance
 * (which has no sidebar item).
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  getStoredUserEmail,
  getStoredUserName,
  logout,
} from '../../lib/auth'
import { getAdminMe } from '../../lib/admin'
import { listHouseholds, type Household } from '../../lib/api'
import { resolveCurrency } from '../../lib/format'
import { useLanguage } from '../../lib/i18n'
import { useTheme } from '../../lib/theme'

export function MinePage() {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const { theme, setTheme } = useTheme()
  const displayName =
    getStoredUserName() ??
    (getStoredUserEmail()?.split('@')[0]?.trim() || null)
  const email = getStoredUserEmail()
  const [households, setHouseholds] = useState<Household[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Admin link (Dashboard Phase C, contract §5): the "管理后台" link
  // is shown ONLY when GET /api/v2/admin/me succeeds. The check runs
  // here on 我的 — never on every app page — and any failure (403 for
  // a normal user, expired session, network) simply hides the link.
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    let cancelled = false
    listHouseholds()
      .then((list) => {
        if (!cancelled) setHouseholds(list)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载家庭信息失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    getAdminMe()
      .then(() => {
        if (!cancelled) setIsAdmin(true)
      })
      .catch(() => {
        if (!cancelled) setIsAdmin(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="page">
      <h1 className="page-title">我的</h1>
      <section className="mine-section" aria-label="账号">
        <h2>账号</h2>
        <dl className="mine-list">
          <div>
            <dt>用户</dt>
            <dd>{displayName ?? '—'}</dd>
          </div>
          <div>
            <dt>邮箱</dt>
            <dd>{email ?? '—'}</dd>
          </div>
        </dl>
        <p className="page-note">
          显示名称来自上次登录或注册时保存的信息；后端尚未提供昵称字段。
        </p>
      </section>
      <section className="mine-section" aria-label="家庭">
        <h2>家庭</h2>
        {loading && <p>加载中…</p>}
        {error && <p className="page-error">{error}</p>}
        {!loading && households.length === 0 && <p className="page-empty">暂无家庭</p>}
        <dl className="mine-list">
          {households.map((h) => (
            <div key={h.id}>
              <dt>{h.name}</dt>
              <dd>
                角色 {h.role} · 默认货币 {resolveCurrency(h.default_currency)} · 时区{' '}
                {h.timezone} · 语言 {h.locale}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="mine-section" aria-label={t['theme.label']}>
        <h2>{t['theme.label']}</h2>
        <div className="theme-segmented" role="group" aria-label={t['theme.label']}>
          <button
            type="button"
            aria-pressed={theme === 'light'}
            onClick={() => {
              setTheme('light')
            }}
          >
            {t['theme.light']}
          </button>
          <button
            type="button"
            aria-pressed={theme === 'dark'}
            onClick={() => {
              setTheme('dark')
            }}
          >
            {t['theme.dark']}
          </button>
        </div>
      </section>
      <section className="mine-section" aria-label="更多">
        <h2>更多</h2>
        <ul className="mine-links">
          {isAdmin && (
            <li>
              <Link to="/admin">{t['admin.mineLink']}</Link>
            </li>
          )}
          <li>
            <Link to="/app/receipts">小票列表</Link>
          </li>
          <li>
            <Link to="/app/maintenance">设备保养</Link>
          </li>
          <li>
            <Link to="/blog">菜谱</Link>
          </li>
        </ul>
      </section>
      <button type="button" className="btn btn-outline" onClick={handleLogout}>
        退出登录
      </button>
    </div>
  )
}
