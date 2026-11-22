/**
 * Admin user detail (/admin/users/:id) — Dashboard Phase C
 * (plan §4.2, contract §2 #4–#6).
 *
 * Account detail, household memberships + ownership, data counts.
 * Disable / re-enable with a REQUIRED reason (confirm panel names
 * the target clearly; disabling bumps `auth_version` server-side so
 * old tokens die immediately). "Inspect household data" is a
 * separate deliberate action: it needs a reason, is read-only and
 * paginated, and writes an audit event server-side.
 *
 * NO bulk export, NO delete, NO password-reset UI in v1.
 */
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getAdminUser,
  listHouseholdRecords,
  patchAdminUserStatus,
  type AdminUserDetail as AdminUser,
  type HouseholdRecordItem,
  type HouseholdRecordType,
} from '../../lib/admin'
import type { Equipment, FridgeItem, Receipt, Transaction } from '../../lib/api'
import { formatAmount, formatDateTime, resolveCurrency } from '../../lib/format'
import { useLanguage } from '../../lib/i18n'
import { AdminLoadError, AdminPager } from './common'

const PAGE_SIZE = 20

const RECORD_TYPES: HouseholdRecordType[] = [
  'receipts',
  'transactions',
  'inventory',
  'equipment',
]

function isReceipt(r: HouseholdRecordItem): r is Receipt {
  return 'store_name' in r && 'total_amount' in r
}

function isTransaction(r: HouseholdRecordItem): r is Transaction {
  return 'occurred_at' in r && 'category' in r && !('store_name' in r)
}

function isFridgeItem(r: HouseholdRecordItem): r is FridgeItem {
  return 'raw_name' in r && 'days_left' in r
}

function isEquipment(r: HouseholdRecordItem): r is Equipment {
  return 'device_type' in r && 'next_maintenance_date' in r
}

export function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { t, lang } = useLanguage()
  const [user, setUser] = useState<AdminUser | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  // Disable / re-enable confirm panel.
  const [confirming, setConfirming] = useState<'disable' | 'enable' | null>(null)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState(false)
  const [actionError, setActionError] = useState(false)
  const [acting, setActing] = useState(false)

  // Household inspection.
  const [inspectHousehold, setInspectHousehold] = useState('')
  const [inspectType, setInspectType] = useState<HouseholdRecordType>('receipts')
  const [inspectReason, setInspectReason] = useState('')
  const [inspectReasonError, setInspectReasonError] = useState(false)
  const [inspectItems, setInspectItems] = useState<HouseholdRecordItem[] | null>(null)
  const [inspectTotal, setInspectTotal] = useState(0)
  const [inspectOffset, setInspectOffset] = useState(0)
  const [inspectLoading, setInspectLoading] = useState(false)
  const [inspectError, setInspectError] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setError(false)
    setNotFound(false)
    getAdminUser(id)
      .then((u) => {
        if (!cancelled) setUser(u)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (
          err !== null &&
          typeof err === 'object' &&
          'status' in err &&
          (err as { status?: number }).status === 404
        ) {
          setNotFound(true)
        } else {
          setError(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [id, attempt])

  const reloadUser = () => setAttempt((n) => n + 1)

  const submitStatusChange = () => {
    if (!user || !confirming) return
    if (reason.trim() === '') {
      setReasonError(true)
      return
    }
    setReasonError(false)
    setActionError(false)
    setActing(true)
    patchAdminUserStatus(user.id, {
      disabled: confirming === 'disable',
      reason: reason.trim(),
    })
      .then((updated) => {
        setUser(updated)
        setConfirming(null)
        setReason('')
      })
      .catch(() => setActionError(true))
      .finally(() => setActing(false))
  }

  const fetchRecords = (offset: number) => {
    if (inspectReason.trim() === '') {
      setInspectReasonError(true)
      return
    }
    setInspectReasonError(false)
    setInspectError(false)
    setInspectLoading(true)
    listHouseholdRecords(inspectHousehold, {
      type: inspectType,
      reason: inspectReason.trim(),
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        setInspectItems(page.items)
        setInspectTotal(page.total)
        setInspectOffset(offset)
      })
      .catch(() => setInspectError(true))
      .finally(() => setInspectLoading(false))
  }

  const typeLabel = (type: HouseholdRecordType) => {
    switch (type) {
      case 'receipts':
        return t['admin.userInspectReceipts']
      case 'transactions':
        return t['admin.userInspectTransactions']
      case 'inventory':
        return t['admin.userInspectInventory']
      case 'equipment':
        return t['admin.userInspectEquipment']
    }
  }

  if (error) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.userDetail']}</h1>
        <AdminLoadError onRetry={reloadUser} />
      </div>
    )
  }
  if (notFound) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.userDetail']}</h1>
        <p className="page-error">{t['admin.userNotFound']}</p>
        <p>
          <Link to="/admin/users">{t['admin.userBack']}</Link>
        </p>
      </div>
    )
  }
  if (!user) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.userDetail']}</h1>
        <p className="page-note">{t['admin.loading']}</p>
      </div>
    )
  }

  const disabled = user.status === 'disabled'

  return (
    <div className="page">
      <p>
        <Link to="/admin/users">{t['admin.userBack']}</Link>
      </p>
      <h1 className="page-title">{user.name}</h1>
      <section aria-label={t['admin.userDetail']}>
        <dl className="mine-list">
          <div>
            <dt>{t['admin.usersEmail']}</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>{t['admin.usersLoginMethod']}</dt>
            <dd>{user.login_method === 'email' ? t['admin.usersEmail'] : 'WeChat'}</dd>
          </div>
          <div>
            <dt>{t['admin.usersStatus']}</dt>
            <dd>
              {disabled ? t['admin.usersDisabled'] : t['admin.usersEnabled']}
              {user.disabled_at
                ? ` · ${formatDateTime(user.disabled_at, lang)}`
                : ''}
            </dd>
          </div>
          <div>
            <dt>{t['admin.usersCreated']}</dt>
            <dd>{formatDateTime(user.created_at, lang)}</dd>
          </div>
        </dl>
      </section>

      <section aria-label={t['admin.userHouseholds']}>
        <h2>{t['admin.userHouseholds']}</h2>
        {user.households.length === 0 ? (
          <p className="page-empty">{t['admin.userNoHouseholds']}</p>
        ) : (
          <dl className="mine-list">
            {user.households.map((h) => (
              <div key={h.household_id}>
                <dt>{h.name}</dt>
                <dd>
                  {h.role === 'owner'
                    ? t['admin.userRoleOwner']
                    : t['admin.userRoleMember']}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section aria-label={t['admin.userDataCounts']}>
        <h2>{t['admin.userDataCounts']}</h2>
        <dl className="mine-list">
          <div>
            <dt>{t['admin.ovReceipts']}</dt>
            <dd>{user.counts.receipts}</dd>
          </div>
          <div>
            <dt>{t['admin.ovTransactions']}</dt>
            <dd>{user.counts.transactions}</dd>
          </div>
          <div>
            <dt>{t['admin.ovInventory']}</dt>
            <dd>{user.counts.inventory_items}</dd>
          </div>
          <div>
            <dt>{t['admin.userInspectEquipment']}</dt>
            <dd>{user.counts.equipments}</dd>
          </div>
        </dl>
      </section>

      <section aria-label={disabled ? t['admin.userEnable'] : t['admin.userDisable']}>
        <h2>{disabled ? t['admin.userEnable'] : t['admin.userDisable']}</h2>
        {actionError && <p className="page-error">{t['admin.userActionFailed']}</p>}
        {confirming === null ? (
          <button
            type="button"
            className={disabled ? 'btn btn-primary' : 'btn btn-error'}
            onClick={() => setConfirming(disabled ? 'enable' : 'disable')}
          >
            {disabled ? t['admin.userEnable'] : t['admin.userDisable']}
          </button>
        ) : (
          <div className="admin-confirm" role="dialog" aria-label={t['admin.userReason']}>
            <p>
              <strong>
                {user.name} · {user.email}
              </strong>
            </p>
            <p>
              {confirming === 'disable'
                ? t['admin.userDisableConfirm']
                : t['admin.userEnableConfirm']}
            </p>
            <label className="form-field" htmlFor="admin-status-reason">
              {t['admin.userReason']}
              <input
                id="admin-status-reason"
                type="text"
                value={reason}
                placeholder={t['admin.userReasonPh']}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            {reasonError && (
              <p className="page-error">{t['admin.userReasonRequired']}</p>
            )}
            <div className="admin-confirm-actions">
              <button
                type="button"
                className={confirming === 'disable' ? 'btn btn-error' : 'btn btn-primary'}
                disabled={acting}
                onClick={submitStatusChange}
              >
                {t['admin.confirm']}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={acting}
                onClick={() => {
                  setConfirming(null)
                  setReason('')
                  setReasonError(false)
                }}
              >
                {t['admin.cancel']}
              </button>
            </div>
          </div>
        )}
      </section>

      <section aria-label={t['admin.userInspect']}>
        <h2>{t['admin.userInspect']}</h2>
        <p className="page-note">{t['admin.userInspectNote']}</p>
        {user.households.length === 0 ? (
          <p className="page-empty">{t['admin.userNoHouseholds']}</p>
        ) : (
          <form
            className="admin-filters"
            onSubmit={(e) => {
              e.preventDefault()
              fetchRecords(0)
            }}
          >
            <label className="form-field admin-filter-field" htmlFor="admin-inspect-household">
              {t['admin.userHouseholds']}
              <select
                id="admin-inspect-household"
                value={inspectHousehold}
                onChange={(e) => setInspectHousehold(e.target.value)}
              >
                <option value="">—</option>
                {user.households.map((h) => (
                  <option key={h.household_id} value={h.household_id}>
                    {h.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field admin-filter-field" htmlFor="admin-inspect-type">
              {t['admin.userInspectType']}
              <select
                id="admin-inspect-type"
                value={inspectType}
                onChange={(e) => {
                  setInspectType(e.target.value as HouseholdRecordType)
                  setInspectItems(null)
                }}
              >
                {RECORD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {typeLabel(type)}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field admin-filter-field" htmlFor="admin-inspect-reason">
              {t['admin.userReason']}
              <input
                id="admin-inspect-reason"
                type="text"
                value={inspectReason}
                placeholder={t['admin.userReasonPh']}
                onChange={(e) => setInspectReason(e.target.value)}
              />
            </label>
            <div className="admin-filter-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={inspectHousehold === '' || inspectLoading}
              >
                {t['admin.userInspect']}
              </button>
            </div>
          </form>
        )}
        {inspectReasonError && (
          <p className="page-error">{t['admin.userReasonRequired']}</p>
        )}
        {inspectError && <p className="page-error">{t['admin.loadError']}</p>}
        {inspectLoading && <p className="page-note">{t['admin.loading']}</p>}
        {inspectItems !== null && !inspectLoading && (
          <>
            {inspectItems.length === 0 ? (
              <p className="page-empty">{t['admin.recordsEmpty']}</p>
            ) : (
              <div className="tx-table-wrap">
                <table className="tx-table">
                  <thead>
                    <tr>
                      <th>{typeLabel(inspectType)}</th>
                      <th>{t['admin.usersCreated']}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inspectItems.map((item) => (
                      <tr key={item.id}>
                        <td>{renderRecordSummary(item)}</td>
                        <td>{formatDateTime(recordCreatedAt(item), lang)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <AdminPager
              total={inspectTotal}
              offset={inspectOffset}
              limit={PAGE_SIZE}
              onPage={(next) => fetchRecords(next)}
            />
          </>
        )}
      </section>
    </div>
  )
}

function recordCreatedAt(item: HouseholdRecordItem): string | null {
  return 'created_at' in item ? (item.created_at as string | null) : null
}

function renderRecordSummary(item: HouseholdRecordItem): string {
  if (isReceipt(item)) {
    const store = item.store_name ?? '—'
    return `${store} · ${formatAmount(item.total_amount, resolveCurrency(item.currency))}`
  }
  if (isTransaction(item)) {
    return `${item.category} · ${formatAmount(item.amount, resolveCurrency(item.currency))}${item.note ? ` · ${item.note}` : ''}`
  }
  if (isFridgeItem(item)) {
    const name = item.canonical_name ?? item.raw_name
    return `${name} · ${item.quantity} ${item.unit}`
  }
  if (isEquipment(item)) {
    return `${item.name ?? item.device_type} · ${item.status}`
  }
  // All four record types are narrowed above; this is unreachable.
  return '—'
}
