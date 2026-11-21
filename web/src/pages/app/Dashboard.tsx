/**
 * User dashboard (/app/dashboard) — Dashboard Phase B (plan §3).
 * The front door after login (D1): /app redirects here.
 *
 * 7 widgets, in plan order, all from existing endpoints (no new
 * backend calls): monthly spending, expiring-soon (Lazy Tracking
 * 1-tap), recent transactions, quick actions, fridge counts,
 * upcoming maintenance, unread notifications. /app/transactions and
 * /app/spending are NOT replaced — the dashboard summarises and
 * links to them.
 *
 * Currency: the spending widget uses the household default (the
 * summary API returns totals in the requested currency); recent
 * transactions show each row in its own currency. Never summed
 * across currencies (P2-06 rule).
 *
 * Notifications widget decision (no notifications page, no
 * mark-as-read endpoint): the widget is non-navigating. The unread
 * count AND the list reuse the bell's client-side "seen" set
 * (localStorage `imsf2.notifications_seen`, see NotificationsBell):
 * the list shows the latest 2 *unread* notifications, not merely
 * open ones. The seen set is re-read whenever notifications reload
 * and whenever the bell marks items seen (window event
 * `imsf:notifications-seen`); the hint points at the topbar bell,
 * which is the entry point.
 *
 * Maintenance widget decision (from the Maintenance page pattern):
 * equipments with no next_maintenance_date are skipped; overdue ones
 * (days_until_maintenance < 0) are kept and shown first — they are
 * the most urgent — sorted by days_until_maintenance ascending.
 *
 * Layout (plan §3.4): desktop ≥1024px 12-column grid inside
 * AppShell (content max-width 1200px); mobile 1 column in the same
 * order, quick actions as a horizontal button row. No chart library:
 * % bars + numbers only. Colours are var(--im-*) only, so both
 * themes work; radius 4px; hairlines, no shadows.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  consumeFridgeItem,
  extendFridgeItem,
  getSpendingSummary,
  isOpenNotification,
  listEquipments,
  listFridge,
  listNotifications,
  listTransactions,
  notificationText,
  type AppNotification,
  type Equipment,
  type FridgeItem,
  type SpendingSummary,
  type Transaction,
  type TransactionCategory,
  type TransactionType,
} from '../../lib/api'
import { loadSeenNotificationIds } from '../../components/NotificationsBell'
import { StatusChip, type ChipTone } from '../../components/StatusChip'
import { useCurrentHousehold } from '../../lib/household'
import {
  currentMonth,
  formatAmount,
  formatRelativeDate,
  monthRange,
  resolveCurrency,
} from '../../lib/format'
import { fill, useLanguage, type Dict, type Language } from '../../lib/i18n'

const LOCALES: Record<Language, string> = {
  'zh-CN': 'zh-CN',
  vi: 'vi',
  en: 'en',
}

const CATEGORY_KEYS: Record<TransactionCategory, keyof Dict> = {
  food: 'dash.cat.food',
  household: 'dash.cat.household',
  maintenance: 'dash.cat.maintenance',
  other: 'dash.cat.other',
}

const TYPE_KEYS: Record<TransactionType, keyof Dict> = {
  expense: 'dash.type.expense',
  income: 'dash.type.income',
}

type ExpiryGroup = 'expired' | 'soon' | 'fresh' | 'none'

function expiryGroup(item: FridgeItem): ExpiryGroup {
  if (item.status === 'consumed') return 'none'
  if (item.days_left === null) return 'none'
  if (item.days_left < 0) return 'expired'
  if (item.days_left <= 3) return 'soon'
  return 'fresh'
}

/** Expiring-soon list: not consumed, expiry known, ≤ 3 days left. */
function expiringItems(items: FridgeItem[]): FridgeItem[] {
  return [...items]
    .filter(
      (item) =>
        item.status !== 'consumed' &&
        item.days_left !== null &&
        item.days_left <= 3,
    )
    .sort((a, b) => (a.days_left ?? 0) - (b.days_left ?? 0))
    .slice(0, 5)
}

/** Upcoming maintenance: dated only, overdue first, soonest first. */
function upcomingEquipments(items: Equipment[]): Equipment[] {
  return [...items]
    .filter(
      (eq) =>
        eq.next_maintenance_date !== null &&
        eq.days_until_maintenance !== null,
    )
    .sort(
      (a, b) =>
        (a.days_until_maintenance ?? 0) - (b.days_until_maintenance ?? 0),
    )
    .slice(0, 3)
}

function monthTitle(month: string, locale: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(month)
  if (!m) return month
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, 1))
  try {
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'long',
    }).format(d)
  } catch {
    return month
  }
}

function Widget({
  title,
  label,
  to,
  linkLabel,
  className,
  children,
}: {
  title: string
  /** Accessible name; defaults to the visible title. The spending
   * widget passes the plain '本月支出' here so its region name does
   * not change with the month. */
  label?: string
  to?: string
  linkLabel?: string
  className?: string
  children: ReactNode
}) {
  return (
    <section
      className={`dash-widget${className ? ` ${className}` : ''}`}
      aria-label={label ?? title}
    >
      <div className="dash-widget-head">
        <h2>{title}</h2>
        {to && linkLabel && (
          <Link className="dash-widget-link" to={to}>
            {linkLabel}
          </Link>
        )}
      </div>
      {children}
    </section>
  )
}

export function DashboardPage() {
  const { t, lang } = useLanguage()
  const {
    household,
    defaultCurrency,
    timezone,
    loading: householdLoading,
    error: householdError,
  } = useCurrentHousehold()
  const [spending, setSpending] = useState<SpendingSummary | null>(null)
  const [spendingError, setSpendingError] = useState<string | null>(null)
  const [fridge, setFridge] = useState<FridgeItem[]>([])
  const [fridgeError, setFridgeError] = useState<string | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [transactionsError, setTransactionsError] = useState<string | null>(null)
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [equipmentsError, setEquipmentsError] = useState<string | null>(null)
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [notificationsError, setNotificationsError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [seenIds, setSeenIds] = useState<Set<string>>(() => loadSeenNotificationIds())

  const month = currentMonth(timezone)
  const loadErrorText = t['dash.loadError']

  const loadAll = useCallback(() => {
    if (!household) return
    setLoaded(false)
    const { from, to } = monthRange(month, timezone)
    Promise.allSettled([
      getSpendingSummary(household.id, defaultCurrency, { from, to }),
      listFridge(household.id, 100),
      listTransactions(household.id, { limit: 8 }),
      listEquipments(household.id),
      listNotifications(household.id, 20),
    ]).then(([sp, fr, tx, eq, no]) => {
      if (sp.status === 'fulfilled') {
        setSpending(sp.value)
        setSpendingError(null)
      } else {
        setSpendingError(
          sp.reason instanceof Error ? sp.reason.message : loadErrorText,
        )
      }
      if (fr.status === 'fulfilled') {
        setFridge(fr.value)
        setFridgeError(null)
      } else {
        setFridgeError(
          fr.reason instanceof Error ? fr.reason.message : loadErrorText,
        )
      }
      if (tx.status === 'fulfilled') {
        setTransactions(tx.value)
        setTransactionsError(null)
      } else {
        setTransactionsError(
          tx.reason instanceof Error ? tx.reason.message : loadErrorText,
        )
      }
      if (eq.status === 'fulfilled') {
        setEquipments(eq.value)
        setEquipmentsError(null)
      } else {
        setEquipmentsError(
          eq.reason instanceof Error ? eq.reason.message : loadErrorText,
        )
      }
      if (no.status === 'fulfilled') {
        setNotifications(no.value)
        setNotificationsError(null)
        // The bell marks notifications seen client-side; re-read the
        // set whenever notifications reload so count and list stay
        // in sync (fix round: defect 4).
        setSeenIds(loadSeenNotificationIds())
      } else {
        setNotificationsError(
          no.reason instanceof Error ? no.reason.message : loadErrorText,
        )
      }
      setLoaded(true)
    })
  }, [household, defaultCurrency, timezone, month, loadErrorText])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  // The bell marks notifications seen when its panel opens; re-read
  // the client-side seen set so the unread count + list update live
  // (fix round: defect 4). Event name shared with NotificationsBell.
  useEffect(() => {
    const onSeen = () => setSeenIds(loadSeenNotificationIds())
    window.addEventListener('imsf:notifications-seen', onSeen)
    return () => window.removeEventListener('imsf:notifications-seen', onSeen)
  }, [])

  const reloadFridge = useCallback(() => {
    if (!household) return
    listFridge(household.id, 100)
      .then((list) => {
        setFridge(list)
        setFridgeError(null)
      })
      .catch((err: unknown) => {
        setFridgeError(err instanceof Error ? err.message : loadErrorText)
      })
  }, [household, loadErrorText])

  const act = async (item: FridgeItem, action: 'consume' | 'extend') => {
    setActingId(item.id)
    setActionError(null)
    try {
      if (action === 'consume') await consumeFridgeItem(item.id)
      else await extendFridgeItem(item.id, 3)
      reloadFridge()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t['dash.actionFailed'])
    } finally {
      setActingId(null)
    }
  }

  const expiring = expiringItems(fridge)
  const counts: Record<ExpiryGroup, number> = {
    expired: 0,
    soon: 0,
    fresh: 0,
    none: 0,
  }
  for (const item of fridge) {
    if (item.status === 'consumed') continue
    counts[expiryGroup(item)] += 1
  }
  const upcoming = upcomingEquipments(equipments)
  const openNotifications = notifications.filter((n) => isOpenNotification(n))
  const unread = openNotifications.filter((n) => !seenIds.has(n.id))
  const latestUnread = unread.slice(0, 2)

  const spendingTotal = spending?.total ?? 0
  const topCategories = [...(spending?.by_category ?? [])]
    .sort((a, b) => b.total - a.total)
    .slice(0, 3)

  const retry = (
    <button type="button" className="btn btn-sm" onClick={loadAll}>
      {t['dash.retry']}
    </button>
  )

  return (
    <div className="page">
      <h1 className="page-title">{t['dash.title']}</h1>
      {householdError && <p className="page-error">{householdError}</p>}
      {householdLoading && <p>{t['dash.loading']}</p>}
      <div className="dash-grid">
        <Widget
          title={fill(t['dash.spendingTitle'], {
            month: monthTitle(month, LOCALES[lang]),
          })}
          label={t['dash.spending']}
          to="/app/spending"
          linkLabel={t['dash.viewAll']}
          className="dash-w-spending"
        >
          {spendingError ? (
            <>
              <p className="page-error" role="alert">
                {spendingError}
              </p>
              {retry}
            </>
          ) : !loaded ? (
            <p>{t['dash.loading']}</p>
          ) : (
            <>
              <p className="dash-total">
                {formatAmount(spendingTotal, defaultCurrency)}
              </p>
              {topCategories.length === 0 ? (
                <p className="page-empty">
                  {t['dash.spendingEmpty']} —{' '}
                  <Link to="/app/transactions">{t['dash.firstTx']}</Link>
                </p>
              ) : (
                <ul className="category-bars">
                  {topCategories.map((c) => {
                    const pct =
                      spendingTotal > 0
                        ? Math.round((c.total / spendingTotal) * 1000) / 10
                        : 0
                    return (
                      <li key={c.category} className="category-bar-row">
                        <span className="category-bar-label">
                          {t[CATEGORY_KEYS[c.category]]}
                        </span>
                        <span
                          className="category-bar-track"
                          role="img"
                          aria-label={`${t[CATEGORY_KEYS[c.category]]} ${formatAmount(c.total, defaultCurrency)}，${pct}%`}
                        >
                          <span
                            className="category-bar-fill"
                            style={{ width: `${pct}%` }}
                          />
                        </span>
                        <span className="category-bar-value">
                          {formatAmount(c.total, defaultCurrency)} · {pct}%
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </>
          )}
        </Widget>

        <Widget
          title={t['dash.expiring']}
          to="/app/fridge"
          linkLabel={t['dash.viewAll']}
          className="dash-w-expiring"
        >
          {fridgeError ? (
            <>
              <p className="page-error" role="alert">
                {fridgeError}
              </p>
              {retry}
            </>
          ) : !loaded ? (
            <p>{t['dash.loading']}</p>
          ) : expiring.length === 0 ? (
            <p className="page-empty">
              {t['dash.expiringEmpty']} —{' '}
              <Link to="/app/upload">{t['dash.firstReceipt']}</Link>
            </p>
          ) : (
            <>
              {actionError && (
                <p className="page-error" role="alert">
                  {actionError}
                </p>
              )}
              <ul className="dash-expiring-list">
                {expiring.map((item) => {
                  const d = item.days_left ?? 0
                  const chip: { tone: ChipTone; label: string } =
                    d < 0
                      ? {
                          tone: 'error',
                          label: fill(t['dash.expiredDays'], {
                            days: String(-d),
                          }),
                        }
                      : d === 0
                        ? { tone: 'warning', label: t['dash.expiresToday'] }
                        : {
                            tone: 'warning',
                            label: fill(t['dash.daysLeft'], {
                              days: String(d),
                            }),
                          }
                  const name = item.canonical_name ?? item.raw_name
                  return (
                    <li key={item.id} className="dash-expiring-row">
                      <div className="dash-expiring-info">
                        <span className="dash-expiring-name">{name}</span>
                        <span className="dash-expiring-meta">
                          {item.quantity} {item.unit}
                        </span>
                      </div>
                      <StatusChip tone={chip.tone} label={chip.label} />
                      <div className="dash-expiring-actions">
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={actingId === item.id}
                          onClick={() => void act(item, 'consume')}
                        >
                          {t['dash.consumed']}
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={actingId === item.id}
                          onClick={() => void act(item, 'extend')}
                        >
                          {t['dash.extend']}
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </Widget>

        <Widget
          title={t['dash.recent']}
          to="/app/transactions"
          linkLabel={t['dash.viewAll']}
          className="dash-w-recent"
        >
          {transactionsError ? (
            <>
              <p className="page-error" role="alert">
                {transactionsError}
              </p>
              {retry}
            </>
          ) : !loaded ? (
            <p>{t['dash.loading']}</p>
          ) : transactions.length === 0 ? (
            <p className="page-empty">
              {t['dash.recentEmpty']} —{' '}
              <Link to="/app/transactions">{t['dash.firstTx']}</Link>
            </p>
          ) : (
            <ul className="dash-tx-list">
              {transactions.map((tx) => (
                <li key={tx.id}>
                  <Link
                    className="dash-tx-row"
                    to="/app/transactions"
                    aria-label={`${tx.occurred_at.slice(0, 10)} ${t[CATEGORY_KEYS[tx.category]]} ${formatAmount(tx.amount, resolveCurrency(tx.currency))}`}
                  >
                    <span className="dash-tx-date">
                      {tx.occurred_at.slice(0, 10)}
                    </span>
                    <span className="dash-tx-cat">
                      {t[CATEGORY_KEYS[tx.category]]}
                    </span>
                    <span className="dash-tx-note">{tx.note ?? ''}</span>
                    <span className="dash-tx-amount">
                      {t[TYPE_KEYS[tx.type]]}{' '}
                      {formatAmount(tx.amount, resolveCurrency(tx.currency))}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Widget>

        <Widget title={t['dash.quick']} className="dash-w-quick">
          <div className="dash-quick-list">
            <Link className="dash-quick-btn" to="/app/transactions">
              {t['dash.quickTx']}
            </Link>
            <Link className="dash-quick-btn" to="/app/upload">
              {t['dash.quickPhoto']}
            </Link>
            <Link className="dash-quick-btn" to="/blog">
              {t['dash.quickRecipes']}
            </Link>
            <Link className="dash-quick-btn" to="/knowledge">
              {t['dash.quickShelf']}
            </Link>
          </div>
        </Widget>

        <Widget
          title={t['dash.fridge']}
          to="/app/fridge"
          linkLabel={t['dash.viewAll']}
          className="dash-w-fridge"
        >
          {fridgeError ? (
            <>
              <p className="page-error" role="alert">
                {fridgeError}
              </p>
              {retry}
            </>
          ) : !loaded ? (
            <p>{t['dash.loading']}</p>
          ) : fridge.filter((i) => i.status !== 'consumed').length === 0 ? (
            <p className="page-empty">
              {t['dash.fridgeEmpty']} —{' '}
              <Link to="/app/upload">{t['dash.firstReceipt']}</Link>
            </p>
          ) : (
            <ul className="dash-counts">
              <li>
                <span
                  className={
                    counts.expired > 0
                      ? 'dash-count-num dash-count-error'
                      : 'dash-count-num'
                  }
                >
                  {counts.expired}
                </span>
                <span>{t['dash.fridgeExpired']}</span>
              </li>
              <li>
                <span
                  className={
                    counts.soon > 0
                      ? 'dash-count-num dash-count-warning'
                      : 'dash-count-num'
                  }
                >
                  {counts.soon}
                </span>
                <span>{t['dash.fridgeSoon']}</span>
              </li>
              <li>
                <span className="dash-count-num">{counts.fresh}</span>
                <span>{t['dash.fridgeFresh']}</span>
              </li>
              {counts.none > 0 && (
                <li>
                  <span className="dash-count-num">{counts.none}</span>
                  <span>{t['dash.fridgeNoExpiry']}</span>
                </li>
              )}
            </ul>
          )}
        </Widget>

        <Widget
          title={t['dash.maintenance']}
          to="/app/maintenance"
          linkLabel={t['dash.viewAll']}
          className="dash-w-maint"
        >
          {equipmentsError ? (
            <>
              <p className="page-error" role="alert">
                {equipmentsError}
              </p>
              {retry}
            </>
          ) : !loaded ? (
            <p>{t['dash.loading']}</p>
          ) : equipments.length === 0 ? (
            <p className="page-empty">{t['dash.maintenanceEmpty']}</p>
          ) : upcoming.length === 0 ? (
            <p className="page-empty">{t['dash.maintenanceNone']}</p>
          ) : (
            <ul className="dash-maint-list">
              {upcoming.map((eq) => {
                const d = eq.days_until_maintenance ?? 0
                const label =
                  d < 0
                    ? fill(t['dash.maintenanceOverdue'], { days: String(-d) })
                    : d === 0
                      ? t['dash.maintenanceToday']
                      : fill(t['dash.maintenanceInDays'], {
                          days: String(d),
                        })
                return (
                  <li key={eq.id} className="dash-maint-row">
                    <span className="dash-maint-name">
                      {eq.name ?? eq.type}
                    </span>
                    <span
                      className={
                        d < 0 ? 'dash-maint-due dash-maint-overdue' : 'dash-maint-due'
                      }
                    >
                      {label} ·{' '}
                      {eq.next_maintenance_date?.slice(0, 10) ?? ''}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </Widget>

        <Widget title={t['dash.notif']} className="dash-w-notif">
          {notificationsError ? (
            <>
              <p className="page-error" role="alert">
                {notificationsError}
              </p>
              {retry}
            </>
          ) : !loaded ? (
            <p>{t['dash.loading']}</p>
          ) : unread.length === 0 ? (
            <p className="page-empty">{t['dash.notifEmpty']}</p>
          ) : (
            <>
              <p className="dash-notif-count">
                <span className="dash-count-num dash-count-accent">
                  {unread.length}
                </span>
                <span>{t['dash.notif']}</span>
              </p>
              <ul className="dash-notif-list">
                {latestUnread.map((n) => (
                  <li key={n.id} className="dash-notif-row">
                    <span className="dash-notif-text">
                      {notificationText(n)}
                    </span>
                    <span className="dash-notif-time">
                      {formatRelativeDate(n.sent_at ?? n.created_at, timezone)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="page-note">{t['dash.notifHint']}</p>
        </Widget>
      </div>
    </div>
  )
}
