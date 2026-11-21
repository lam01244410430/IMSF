/**
 * Notifications bell in the app topbar (plan §5.3 — NOT a separate
 * route). Dropdown panel: list from GET /api/v2/notifications, and the
 * Lazy Tracking respond actions (已用完 / 再放三天) inline for open
 * lazy_tracking items.
 *
 * Honest limitation: the backend has NO mark-as-read endpoint, so
 * "read on open" is tracked client-side only — notification ids seen
 * in this browser are stored in localStorage (`imsf2.notifications_seen`)
 * and no longer counted as unread. The server state is untouched.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getStoredHouseholdId } from '../lib/auth'
import {
  isOpenNotification,
  listHouseholds,
  listNotifications,
  notificationText,
  respondNotification,
  type AppNotification,
} from '../lib/api'
import { formatRelativeDate } from '../lib/format'

const SEEN_KEY = 'imsf2.notifications_seen'

function loadSeen(): Set<string> {
  try {
    const raw = window.localStorage.getItem(SEEN_KEY)
    const arr = raw ? (JSON.parse(raw) as unknown) : []
    return new Set(Array.isArray(arr) ? arr.filter((x): x is string => typeof x === 'string') : [])
  } catch {
    return new Set()
  }
}

/**
 * Read-only view of the same "seen" set, for the dashboard's unread
 * count — the dashboard never writes it (only the bell marks as seen,
 * when its panel opens).
 */
export function loadSeenNotificationIds(): Set<string> {
  return loadSeen()
}

function saveSeen(seen: Set<string>): void {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify([...seen]))
  } catch {
    // ignore — badge just stays unread
  }
}

const TYPE_LABELS: Record<AppNotification['type'], string> = {
  expiry_reminder: '过期提醒',
  lazy_tracking: '快过期',
  maintenance_reminder: '保养提醒',
  system: '系统',
}

export function NotificationsBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<AppNotification[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [seen, setSeen] = useState<Set<string>>(() => loadSeen())
  const [actingId, setActingId] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const stored = getStoredHouseholdId()
      let householdId = stored
      if (!householdId) {
        const list = await listHouseholds()
        householdId = list[0]?.id ?? null
      }
      if (!householdId) {
        setItems([])
        return
      }
      setItems(await listNotifications(householdId, 20))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载通知失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // Mark-as-read on open (client-side only — see header comment).
  const toggle = () => {
    if (!open) {
      void load()
      setOpen(true)
    } else {
      setOpen(false)
    }
  }

  useEffect(() => {
    if (!open) return
    // Everything currently listed counts as seen once the panel is open.
    const next = new Set(seen)
    let changed = false
    for (const n of items) {
      if (!next.has(n.id)) {
        next.add(n.id)
        changed = true
      }
    }
    if (changed) {
      setSeen(next)
      saveSeen(next)
      // Tell the dashboard (same tab) the seen set changed so its
      // unread count + list update live — same-tab localStorage
      // writes do not fire a `storage` event. Event name shared
      // with Dashboard.tsx (fix round: defect 4).
      window.dispatchEvent(new Event('imsf:notifications-seen'))
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, items])

  const unread = items.filter((n) => isOpenNotification(n) && !seen.has(n.id)).length

  const respond = async (n: AppNotification, response: 'used_up' | 'extended') => {
    setActingId(n.id)
    try {
      const updated = await respondNotification(n.id, response, 3)
      setItems((prev) => prev.map((x) => (x.id === n.id ? updated : x)))
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setActingId(null)
    }
  }

  return (
    <div className="notif-bell" ref={panelRef}>
      <button
        type="button"
        className="notif-bell-btn"
        aria-label={unread > 0 ? `通知（${unread} 条未读）` : '通知'}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={toggle}
      >
        <svg className="notif-bell-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M13.7 21a2 2 0 0 1-3.4 0"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {unread > 0 && (
          <span className="notif-bell-badge" aria-hidden="true">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <button
            type="button"
            className="notif-backdrop"
            aria-label="关闭通知"
            onClick={() => setOpen(false)}
          />
          <div className="notif-panel" role="dialog" aria-label="通知">
            <div className="notif-panel-head">
              <h2>通知</h2>
              <span className="notif-panel-note">已读状态仅保存在本浏览器</span>
            </div>
            {loading && <p className="notif-empty">加载中…</p>}
            {error && <p className="notif-error">{error}</p>}
            {!loading && !error && items.length === 0 && (
              <p className="notif-empty">暂无通知</p>
            )}
            <ul className="notif-list">
              {items.map((n) => {
                const canRespond = n.type === 'lazy_tracking' && isOpenNotification(n)
                const responded = n.status === 'responded'
                return (
                  <li key={n.id} className="notif-item">
                    <div className="notif-item-top">
                      <span className="notif-type">{TYPE_LABELS[n.type]}</span>
                      <span className="notif-time">
                        {formatRelativeDate(n.sent_at ?? n.created_at)}
                      </span>
                    </div>
                    <p className="notif-text">{notificationText(n)}</p>
                    {responded && (
                      <p className="notif-responded">
                        已回复：{n.response === 'used_up' ? '已用完' : '再放三天'}
                      </p>
                    )}
                    {canRespond && (
                      <div className="notif-actions">
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={actingId === n.id}
                          onClick={() => void respond(n, 'used_up')}
                        >
                          已用完
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={actingId === n.id}
                          onClick={() => void respond(n, 'extended')}
                        >
                          再放三天
                        </button>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
