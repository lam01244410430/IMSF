/**
 * Receipts list (/app/receipts) — not in the sidebar; linked from the
 * upload page (最近小票) and from receipt rows. Status filter chips;
 * the 「处理中」 chip covers both pending and processing, because the
 * backend filters on exactly one status.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  listReceipts,
  RECEIPT_STATUS_LABELS,
  type Receipt,
  type ReceiptStatus,
} from '../../lib/api'
import { useCurrentHousehold } from '../../lib/household'
import { formatMoney, formatRelativeDate, resolveCurrency } from '../../lib/format'
import { StatusChip, type ChipTone } from '../../components/StatusChip'

type Filter = 'all' | 'processing' | ReceiptStatus

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'processing', label: '处理中' },
  { key: 'needs_review', label: '待核对' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '识别失败' },
]

function receiptTone(status: ReceiptStatus): ChipTone {
  switch (status) {
    case 'failed':
      return 'error'
    case 'needs_review':
      return 'warning'
    case 'completed':
      return 'success'
    case 'processing':
      return 'accent'
    case 'pending':
    default:
      return 'neutral'
  }
}

export function ReceiptsPage() {
  const { household, loading: householdLoading, error: householdError } = useCurrentHousehold()
  const [filter, setFilter] = useState<Filter>('all')
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!household) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const fetchList = async () => {
      if (filter === 'processing') {
        // One status per backend call — fetch both halves and merge.
        const [pending, processing] = await Promise.all([
          listReceipts(household.id, { status: 'pending', limit: 50 }),
          listReceipts(household.id, { status: 'processing', limit: 50 }),
        ])
        return [...pending, ...processing].sort((a, b) =>
          (b.created_at ?? '').localeCompare(a.created_at ?? ''),
        )
      }
      return listReceipts(household.id, {
        status: filter === 'all' ? undefined : filter,
        limit: 50,
      })
    }
    fetchList()
      .then((list) => {
        if (!cancelled) setReceipts(list)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载小票失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [household, filter])

  return (
    <div className="page">
      <h1 className="page-title">小票</h1>
      <div className="filter-chips" role="group" aria-label="按状态筛选">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`filter-chip${filter === f.key ? ' filter-chip-active' : ''}`}
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>
      {householdLoading && <p>加载中…</p>}
      {householdError && <p className="page-error">{householdError}</p>}
      {error && <p className="page-error">{error}</p>}
      {!householdLoading && !householdError && !loading && receipts.length === 0 && (
        <p className="page-empty">没有符合条件的小票</p>
      )}
      {loading && <p>加载中…</p>}
      <ul className="receipt-list">
        {receipts.map((r) => (
          <li key={r.id} className="receipt-row">
            <Link to={`/app/receipts/${r.id}`} className="receipt-row-link">
              <span className="receipt-store">{r.store_name ?? '未命名商店'}</span>
              <span className="receipt-meta">
                {formatRelativeDate(r.created_at, household?.timezone)}
                {' · '}
                {formatMoney(r.total_amount, resolveCurrency(r.currency))}
              </span>
              <StatusChip tone={receiptTone(r.status)} label={RECEIPT_STATUS_LABELS[r.status]} />
            </Link>
          </li>
        ))}
      </ul>
      <p>
        <Link to="/app/upload">← 返回拍照</Link>
      </p>
    </div>
  )
}
