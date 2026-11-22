/**
 * Admin Users (/admin/users) — Dashboard Phase C (plan §4.1–§4.2,
 * contract §2 #3).
 *
 * Search by email exact / WeChat openid exact / name substring
 * (the `q` param; openid lookup is server-side only — the list
 * NEVER returns an openid), filters by login method and
 * enabled/disabled status, paginated. Rows link to the user detail
 * page. No bulk export, no delete, no password reset UI (v1 scope,
 * plan §4.7).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  listAdminUsers,
  type AdminLoginMethod,
  type AdminUserListItem,
  type AdminUserStatus,
} from '../../lib/admin'
import { formatDateTime } from '../../lib/format'
import { useLanguage } from '../../lib/i18n'
import { AdminLoadError, AdminPager } from './common'

const PAGE_SIZE = 20

export function AdminUsersPage() {
  const { t, lang } = useLanguage()
  const [q, setQ] = useState('')
  const [appliedQ, setAppliedQ] = useState('')
  const [loginMethod, setLoginMethod] = useState<'' | AdminLoginMethod>('')
  const [status, setStatus] = useState<'' | AdminUserStatus>('')
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<AdminUserListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const page = await listAdminUsers({
          q: appliedQ || undefined,
          login_method: loginMethod || undefined,
          status: status || undefined,
          limit: PAGE_SIZE,
          offset,
        })
        if (!cancelled) {
          setItems(page.items)
          setTotal(page.total)
          setError(false)
        }
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    setLoading(true)
    setError(false)
    void run()
    return () => {
      cancelled = true
    }
    // `attempt` is the retry trigger (bumped by the retry button).
  }, [appliedQ, loginMethod, status, offset, attempt])

  const applySearch = () => {
    setOffset(0)
    setAppliedQ(q.trim())
  }

  const clearFilters = () => {
    setQ('')
    setAppliedQ('')
    setLoginMethod('')
    setStatus('')
    setOffset(0)
  }

  const statusLabel = (s: AdminUserStatus) =>
    s === 'enabled' ? t['admin.usersEnabled'] : t['admin.usersDisabled']

  return (
    <div className="page">
      <h1 className="page-title">{t['admin.usersTitle']}</h1>
      <form
        className="admin-filters"
        onSubmit={(e) => {
          e.preventDefault()
          applySearch()
        }}
      >
        <label
          className="form-field admin-filter-field admin-filter-field-wide"
          htmlFor="admin-users-q"
        >
          {t['admin.usersSearch']}
          <input
            id="admin-users-q"
            type="search"
            value={q}
            placeholder={t['admin.usersSearchPh']}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label className="form-field admin-filter-field" htmlFor="admin-users-method">
          {t['admin.usersLoginMethod']}
          <select
            id="admin-users-method"
            value={loginMethod}
            onChange={(e) => {
              setLoginMethod(e.target.value as '' | AdminLoginMethod)
              setOffset(0)
            }}
          >
            <option value="">{t['admin.usersAll']}</option>
            <option value="email">{t['admin.usersEmail']}</option>
            <option value="wechat">WeChat</option>
          </select>
        </label>
        <label className="form-field admin-filter-field" htmlFor="admin-users-status">
          {t['admin.usersStatus']}
          <select
            id="admin-users-status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as '' | AdminUserStatus)
              setOffset(0)
            }}
          >
            <option value="">{t['admin.usersAll']}</option>
            <option value="enabled">{t['admin.usersEnabled']}</option>
            <option value="disabled">{t['admin.usersDisabled']}</option>
          </select>
        </label>
        <div className="admin-filter-actions">
          <button type="submit" className="btn btn-primary">
            {t['admin.usersSearch']}
          </button>
          <button type="button" className="btn btn-ghost" onClick={clearFilters}>
            {t['admin.usersClear']}
          </button>
        </div>
      </form>
      {error ? (
        <AdminLoadError onRetry={() => setAttempt((n) => n + 1)} />
      ) : loading ? (
        <p className="page-note">{t['admin.loading']}</p>
      ) : items.length === 0 ? (
        <p className="page-empty">{t['admin.usersEmpty']}</p>
      ) : (
        <>
          <div className="tx-table-wrap">
            <table className="tx-table">
              <thead>
                <tr>
                  <th>{t['admin.usersName']}</th>
                  <th>{t['admin.usersEmail']}</th>
                  <th>{t['admin.usersLoginMethod']}</th>
                  <th>{t['admin.usersStatus']}</th>
                  <th>{t['admin.usersCreated']}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <Link to={`/admin/users/${u.id}`}>{u.name}</Link>
                    </td>
                    <td>{u.email}</td>
                    <td>{u.login_method === 'email' ? t['admin.usersEmail'] : 'WeChat'}</td>
                    <td>{statusLabel(u.status)}</td>
                    <td>{formatDateTime(u.created_at, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <AdminPager total={total} offset={offset} limit={PAGE_SIZE} onPage={setOffset} />
        </>
      )}
    </div>
  )
}
