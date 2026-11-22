/**
 * Shared admin-page pieces (Dashboard Phase C) — components only.
 * The date helper lives in `lib/format.ts` (`formatDateTime`) so this
 * file exports no plain values (oxlint only-export-components).
 */
import { fill, useLanguage } from '../../lib/i18n'

/** Pager for the admin list endpoints (`limit` + `offset`, contract §2). */
export function AdminPager({
  total,
  offset,
  limit,
  onPage,
}: {
  total: number
  offset: number
  limit: number
  onPage: (nextOffset: number) => void
}) {
  const { t } = useLanguage()
  const hasPrev = offset > 0
  const hasNext = offset + limit < total
  return (
    <div className="admin-pager">
      <span>{fill(t['admin.total'], { total: String(total) })}</span>
      <span className="admin-pager-spacer" />
      <button
        type="button"
        className="btn btn-sm"
        disabled={!hasPrev}
        onClick={() => onPage(Math.max(0, offset - limit))}
      >
        {t['admin.prev']}
      </button>
      <button
        type="button"
        className="btn btn-sm"
        disabled={!hasNext}
        onClick={() => onPage(offset + limit)}
      >
        {t['admin.next']}
      </button>
    </div>
  )
}

/** Honest load failure with a retry button (never a silent empty list). */
export function AdminLoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = useLanguage()
  return (
    <div>
      <p className="page-error">{t['admin.loadError']}</p>
      <button type="button" className="btn btn-primary" onClick={onRetry}>
        {t['admin.retry']}
      </button>
    </div>
  )
}
