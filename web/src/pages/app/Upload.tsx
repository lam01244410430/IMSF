/**
 * Upload page (/app/upload) — receipt capture.
 *
 * HONEST STATE (scan deferred by Lam; GPU off): automatic receipt
 * recognition is NOT running, so the page does NOT claim scanning
 * works. The capture action is DISABLED with a notice explaining why,
 * and no upload is attempted — so no stuck pending receipts can be
 * created from here. The capture UI structure is still rendered (so
 * the layout is real), and the recent-receipts list below links to
 * the real receipts from GET /api/v2/receipts.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listReceipts, type Receipt } from '../../lib/api'
import { useCurrentHousehold } from '../../lib/household'
import { formatMoney, formatRelativeDate, resolveCurrency } from '../../lib/format'
import { StatusChip } from '../../components/StatusChip'
import { RECEIPT_STATUS_LABELS } from '../../lib/api'

function receiptTone(status: Receipt['status']): 'error' | 'warning' | 'success' | 'accent' | 'neutral' {
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

export function UploadPage() {
  const { household, loading: householdLoading, error: householdError } = useCurrentHousehold()
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!household) return
    let cancelled = false
    setLoading(true)
    listReceipts(household.id, { limit: 5 })
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
  }, [household])

  return (
    <div className="page">
      <h1 className="page-title">拍照</h1>

      <div className="upload-layout">
        <section className="upload-capture" aria-label="拍摄小票">
          <div className="upload-capture-frame" aria-hidden="true">
            <span className="upload-capture-glyph">▣</span>
            <span>小票照片将显示在这里</span>
          </div>
          <p className="upload-scan-notice" role="status">
            小票自动识别功能暂未开启，敬请期待。
            <span className="upload-scan-note">
              自动识别需要 GPU 服务器运行，目前服务器已关闭，因此暂时无法上传识别。
              已有小票仍可在下方查看。
            </span>
          </p>
          <div className="upload-actions">
            <button type="button" className="btn btn-primary btn-lg upload-action" disabled>
              拍照
            </button>
            <button type="button" className="btn btn-outline btn-lg upload-action" disabled>
              从相册选择
            </button>
          </div>
        </section>

        <section className="upload-detail" aria-label="拍摄说明">
          <h2>如何使用</h2>
          <ol className="upload-steps">
            <li>买菜回来，拍一张小票。</li>
            <li>系统识别商品并核对总价，确认后食材进冰箱、支出进账本。</li>
            <li>食材快过期时，看看菜谱推荐，做一道菜，不浪费。</li>
          </ol>
          <p className="upload-detail-note">
            小票识别开启后，这里会显示识别进度与核对入口。
            在此之前，请使用<Link to="/app/transactions">记账</Link>手动记录支出。
          </p>
          <p>
            <Link className="btn btn-outline" to="/app/receipts">
              查看全部小票
            </Link>
          </p>
        </section>
      </div>

      <section className="recent-receipts" aria-label="最近小票">
        <h2>最近小票</h2>
        {householdLoading && <p>加载中…</p>}
        {householdError && <p className="page-error">{householdError}</p>}
        {error && <p className="page-error">{error}</p>}
        {!householdLoading && !householdError && !loading && receipts.length === 0 && (
          <p className="page-empty">还没有小票</p>
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
      </section>
    </div>
  )
}
