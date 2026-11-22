/**
 * Admin Overview (/admin) — Dashboard Phase C (plan §4.1, contract §5).
 *
 * Operational counts + actionable exceptions, each linking to its
 * detail page. It deliberately does NOT duplicate the user
 * dashboard's spending/expiry widgets, and it shows NO global
 * finance dump (contract §2 #2).
 *
 * Counts label accounts honestly: accounts are not people — one
 * person can have two accounts (plan §4.1).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAdminStats, type AdminStats } from '../../lib/admin'
import { fill, useLanguage } from '../../lib/i18n'
import { AdminLoadError } from './common'

export function AdminOverviewPage() {
  const { t } = useLanguage()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setError(false)
    getAdminStats()
      .then((s) => {
        if (!cancelled) setStats(s)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  if (error) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.ovTitle']}</h1>
        <AdminLoadError onRetry={() => setAttempt((n) => n + 1)} />
      </div>
    )
  }
  if (!stats) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.ovTitle']}</h1>
        <p className="page-note">{t['admin.loading']}</p>
      </div>
    )
  }

  const { counts, exceptions } = stats
  const exceptionItems: { key: string; text: string }[] = []
  if (exceptions.failed_receipt_jobs > 0) {
    exceptionItems.push({
      key: 'failed-jobs',
      text: fill(t['admin.ovFailedJobs'], {
        n: String(exceptions.failed_receipt_jobs),
      }),
    })
  }
  if (exceptions.overdue_cron) {
    exceptionItems.push({ key: 'cron', text: t['admin.ovCronOverdue'] })
  }
  if (exceptions.unavailable_dependencies.length > 0) {
    exceptionItems.push({
      key: 'deps',
      text: fill(t['admin.ovDepsDown'], {
        names: exceptions.unavailable_dependencies.join(', '),
      }),
    })
  }

  const countCards: { label: string; value: number }[] = [
    { label: t['admin.ovAccounts'], value: counts.users },
    { label: t['admin.ovHouseholds'], value: counts.households },
    { label: t['admin.ovReceipts'], value: counts.receipts },
    { label: t['admin.ovTransactions'], value: counts.transactions },
    { label: t['admin.ovInventory'], value: counts.inventory_items },
    { label: t['admin.ovPublished'], value: counts.published_recipes },
    { label: t['admin.ovDrafts'], value: counts.draft_recipes },
    { label: t['admin.ovHidden'], value: counts.hidden_recipes },
  ]

  return (
    <div className="page">
      <h1 className="page-title">{t['admin.ovTitle']}</h1>
      <section aria-label={t['admin.ovCounts']}>
        <h2>{t['admin.ovCounts']}</h2>
        {/* Taste review: the "accounts are not people" note lived
            inside the accounts card and made it (and its row) taller
            than every sibling. As a caption under the heading it
            keeps the cards uniform and reads as a definition. */}
        <p className="page-note">{t['admin.ovAccountsNote']}</p>
        <div className="dash-grid admin-count-grid">
          {countCards.map((card) => (
            <div key={card.label} className="dash-widget admin-count-card">
              <div className="dash-total">{card.value}</div>
              <div className="admin-count-label">{card.label}</div>
            </div>
          ))}
        </div>
      </section>
      <section aria-label={t['admin.ovExceptions']}>
        <h2>{t['admin.ovExceptions']}</h2>
        {exceptionItems.length === 0 ? (
          <p className="page-empty">{t['admin.ovNoExceptions']}</p>
        ) : (
          <ul className="admin-exception-list">
            {exceptionItems.map((item) => (
              <li key={item.key}>
                <Link to="/admin/system">{item.text}</Link>
              </li>
            ))}
          </ul>
        )}
        {exceptionItems.length > 0 && (
          <p>
            <Link to="/admin/system">{t['admin.ovViewSystem']}</Link>
          </p>
        )}
      </section>
    </div>
  )
}
