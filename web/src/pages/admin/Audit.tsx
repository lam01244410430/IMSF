/**
 * Admin Audit (/admin/audit) — Dashboard Phase C (plan §4.1,
 * contract §2 #13).
 *
 * Filterable (action / target ID / date range), paginated list of
 * admin audit events: actor, action, target, time, outcome, reason.
 * No edit/delete — the audit trail is append-only in the UI.
 */
import { useEffect, useState } from 'react'
import {
  listAdminAuditEvents,
  type AdminAuditEvent,
} from '../../lib/admin'
import { formatDateTime } from '../../lib/format'
import { useLanguage } from '../../lib/i18n'
import { StatusChip } from '../../components/StatusChip'
import { AdminLoadError, AdminPager } from './common'

const PAGE_SIZE = 20

export function AdminAuditPage() {
  const { t, lang } = useLanguage()
  const [action, setAction] = useState('')
  const [appliedAction, setAppliedAction] = useState('')
  const [targetId, setTargetId] = useState('')
  const [appliedTargetId, setAppliedTargetId] = useState('')
  const [from, setFrom] = useState('')
  const [appliedFrom, setAppliedFrom] = useState('')
  const [to, setTo] = useState('')
  const [appliedTo, setAppliedTo] = useState('')
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<AdminAuditEvent[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    listAdminAuditEvents({
      action: appliedAction || undefined,
      target_id: appliedTargetId || undefined,
      from: appliedFrom || undefined,
      to: appliedTo || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (!cancelled) {
          setItems(page.items)
          setTotal(page.total)
        }
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [appliedAction, appliedTargetId, appliedFrom, appliedTo, offset, attempt])

  const applyFilters = () => {
    setOffset(0)
    setAppliedAction(action.trim())
    setAppliedTargetId(targetId.trim())
    setAppliedFrom(from)
    setAppliedTo(to)
  }

  const clearFilters = () => {
    setAction('')
    setAppliedAction('')
    setTargetId('')
    setAppliedTargetId('')
    setFrom('')
    setAppliedFrom('')
    setTo('')
    setAppliedTo('')
    setOffset(0)
  }

  return (
    <div className="page">
      <h1 className="page-title">{t['admin.auditTitle']}</h1>
      <form
        className="admin-filters"
        onSubmit={(e) => {
          e.preventDefault()
          applyFilters()
        }}
      >
        <label className="form-field admin-filter-field" htmlFor="admin-audit-action">
          {t['admin.auditFilterAction']}
          <input
            id="admin-audit-action"
            type="text"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
        </label>
        <label className="form-field admin-filter-field" htmlFor="admin-audit-target">
          {t['admin.auditFilterTarget']}
          <input
            id="admin-audit-target"
            type="text"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
          />
        </label>
        <label className="form-field admin-filter-field" htmlFor="admin-audit-from">
          {t['admin.auditFilterFrom']}
          <input
            id="admin-audit-from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label className="form-field admin-filter-field" htmlFor="admin-audit-to">
          {t['admin.auditFilterTo']}
          <input
            id="admin-audit-to"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <div className="admin-filter-actions">
          <button type="submit" className="btn btn-primary">
            {t['admin.auditApply']}
          </button>
          <button type="button" className="btn btn-ghost" onClick={clearFilters}>
            {t['admin.auditClear']}
          </button>
        </div>
      </form>
      {error ? (
        <AdminLoadError onRetry={() => setAttempt((n) => n + 1)} />
      ) : loading ? (
        <p className="page-note">{t['admin.loading']}</p>
      ) : items.length === 0 ? (
        <p className="page-empty">{t['admin.auditEmpty']}</p>
      ) : (
        <>
          <div className="tx-table-wrap">
            <table className="tx-table">
              <thead>
                <tr>
                  <th>{t['admin.auditActor']}</th>
                  <th>{t['admin.auditAction']}</th>
                  <th>{t['admin.auditTarget']}</th>
                  <th>{t['admin.auditTime']}</th>
                  <th>{t['admin.auditOutcome']}</th>
                  <th>{t['admin.auditReason']}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((ev) => (
                  <tr key={ev.id}>
                    <td title={ev.actor_user_id}>{ev.actor_user_id.slice(0, 8)}</td>
                    <td>{ev.action}</td>
                    <td title={`${ev.target_type}:${ev.target_id}`}>
                      {ev.target_type}:{ev.target_id.slice(0, 8)}
                    </td>
                    <td>{formatDateTime(ev.created_at, lang)}</td>
                    <td>
                      {ev.outcome === 'success' ? (
                        <StatusChip tone="success" label={t['admin.auditSuccess']} />
                      ) : (
                        <StatusChip tone="error" label={t['admin.auditFailure']} />
                      )}
                    </td>
                    <td>{ev.reason ?? '—'}</td>
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
