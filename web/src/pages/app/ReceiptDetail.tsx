/**
 * Receipt detail (/app/receipts/:id) — processing state + review/confirm.
 *
 * Honest states, no fake progress:
 * - pending / processing: the receipt is NOT being processed right now
 *   (automatic recognition is off — the GPU server is down), so the
 *   page says so plainly instead of showing a progress bar. No
 *   polling: polling a dead worker would only pretend work is happening.
 * - failed: shows the backend error_message when present.
 * - needs_review: line editor + summary + confirm action.
 * - completed: read-only lines + how many items went to the fridge.
 *
 * D-F2: reprocess buttons stay HIDDEN (no client re-POST exists).
 * D-F3: there is NO add-line control. The backend's ConfirmLine
 * requires `line_id` to be a UUID of a line belonging to this receipt
 * and confirm only UPDATEs — a client-added line would 422. The page
 * says this in plain text instead of pretending added lines work.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  confirmReceipt,
  getReceipt,
  RECEIPT_STATUS_LABELS,
  type ConfirmLineInput,
  type ReceiptDetail,
} from '../../lib/api'
import { formatMoney, lineTotal, reconciliationDiff, resolveCurrency, round2, unitPriceFromLine } from '../../lib/format'
import { StatusChip, type ChipTone } from '../../components/StatusChip'

function receiptTone(status: ReceiptDetail['status']): ChipTone {
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

interface LineDraft {
  line_id: string
  raw_name: string
  quantity: string
  unit: string
  unitPrice: string
  is_stock_item: boolean
}

function toDraft(line: ReceiptDetail['lines'][number]): LineDraft {
  return {
    line_id: line.id,
    raw_name: line.raw_name,
    quantity: String(line.quantity),
    unit: line.unit,
    unitPrice: String(unitPriceFromLine(line.price, line.quantity)),
    is_stock_item: line.is_stock_item,
  }
}

function draftPrice(d: LineDraft): number {
  const q = Number(d.quantity)
  const p = Number(d.unitPrice)
  if (Number.isNaN(q) || Number.isNaN(p)) return NaN
  return lineTotal(q, p)
}

export function ReceiptDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<ReceiptDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<LineDraft[]>([])
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState<{ inventory_created: number; sum: number } | null>(null)

  const load = useCallback(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    getReceipt(id)
      .then((d) => {
        setDetail(d)
        setDrafts(d.lines.map(toDraft))
        setConfirmed(null)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载小票失败')
      })
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const updateDraft = (index: number, patch: Partial<LineDraft>) => {
    setDrafts((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  }

  const handleConfirm = async () => {
    if (!detail) return
    setConfirmError(null)
    const lines: ConfirmLineInput[] = []
    for (const d of drafts) {
      const q = Number(d.quantity)
      const price = draftPrice(d)
      if (!d.unit.trim()) {
        setConfirmError('请填写每一行的单位')
        return
      }
      if (!(q > 0) || Number.isNaN(price) || price < 0) {
        setConfirmError('请检查每一行的数量与单价（数量须大于 0）')
        return
      }
      lines.push({
        line_id: d.line_id,
        quantity: round2(q),
        unit: d.unit.trim(),
        price,
        is_stock_item: d.is_stock_item,
      })
    }
    if (lines.length === 0) {
      setConfirmError('没有可确认的行')
      return
    }
    setConfirming(true)
    try {
      const res = await confirmReceipt(detail.id, lines)
      const sum = round2(lines.reduce((acc, l) => acc + l.price, 0))
      setConfirmed({ inventory_created: res.inventory_created, sum })
      setDetail(res)
    } catch (err) {
      const status = (err as Error & { status?: number }).status
      if (status === 409) {
        setConfirmError('这张小票已不在待核对状态，请刷新后查看。')
      } else if (status === 422) {
        setConfirmError('提交被拒绝，请检查各行的数量、单位与金额。')
      } else {
        setConfirmError(err instanceof Error ? err.message : '确认失败')
      }
    } finally {
      setConfirming(false)
    }
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">小票</h1>
        <p>加载中…</p>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="page">
        <h1 className="page-title">小票</h1>
        <p className="page-error">{error ?? '找不到这张小票'}</p>
        <p>
          <Link to="/app/receipts">← 返回小票列表</Link>
        </p>
      </div>
    )
  }

  const currency = resolveCurrency(detail.currency)
  const linesSum = round2(drafts.reduce((acc, d) => acc + (draftPrice(d) || 0), 0))
  const recon = reconciliationDiff(detail.total_amount, linesSum)
  const isReview = detail.status === 'needs_review' && !confirmed
  const stuck = detail.status === 'pending' || detail.status === 'processing'

  return (
    <div className="page">
      <h1 className="page-title">{detail.store_name ?? '未命名商店'}</h1>
      <p className="receipt-head">
        <StatusChip tone={receiptTone(detail.status)} label={RECEIPT_STATUS_LABELS[detail.status]} />
        <span>
          总计 {formatMoney(detail.total_amount, currency)}
          {detail.purchased_at ? ` · 购买于 ${detail.purchased_at.slice(0, 10)}` : ''}
        </span>
      </p>

      {confirmed && (
        <div className="notice notice-success" role="status">
          已确认：{confirmed.inventory_created} 件食材已记入冰箱，记账{' '}
          {formatMoney(confirmed.sum, currency)}。
        </div>
      )}

      {stuck && (
        <div className="notice notice-neutral" role="status">
          <strong>这张小票目前没有在识别中。</strong>
          小票自动识别功能暂未开启（GPU 服务器已关闭），因此它会一直停留
          在「{RECEIPT_STATUS_LABELS[detail.status]}」状态，直到识别服务恢复。
          这里不显示虚假的识别进度。
        </div>
      )}

      {detail.status === 'failed' && (
        <div className="notice notice-error" role="status">
          <strong>识别失败。</strong>
          {detail.error_message ? `原因：${detail.error_message}` : '暂无失败原因。'}
        </div>
      )}

      {detail.status === 'completed' && (
        <p className="page-note">已确认入库：{detail.inventory_created} 件食材已记入冰箱。</p>
      )}

      {detail.lines.length === 0 && !stuck && (
        <p className="page-empty">这张小票没有明细行。</p>
      )}

      {detail.lines.length > 0 && (
        <section aria-label="小票明细">
          <h2>明细</h2>
          {isReview ? (
            <>
              <p className="page-note">
                请核对每一行：数量、单位、单价与是否入库。金额为行小计（数量 ×
                单价），提交时将与小票总计核对（误差须在 2% 以内）。
              </p>
              <p className="page-note">
                暂不支持新增行：后端目前只接受属于这张小票的行，新增的行提交时会被拒绝。如需补行，请等待后端支持后再操作。
              </p>
              <ul className="review-lines">
                {drafts.map((d, i) => {
                  const price = draftPrice(d)
                  return (
                    <li key={d.line_id} className="review-line">
                      <span className="review-line-name">{d.raw_name}</span>
                      <label className="review-field">
                        数量
                        <input
                          type="number"
                          min="0"
                          step="any"
                          inputMode="decimal"
                          value={d.quantity}
                          onChange={(e) => updateDraft(i, { quantity: e.target.value })}
                        />
                      </label>
                      <label className="review-field">
                        单位
                        <input
                          type="text"
                          value={d.unit}
                          onChange={(e) => updateDraft(i, { unit: e.target.value })}
                        />
                      </label>
                      <label className="review-field">
                        单价
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          inputMode="decimal"
                          value={d.unitPrice}
                          onChange={(e) => updateDraft(i, { unitPrice: e.target.value })}
                        />
                      </label>
                      <span className="review-line-subtotal">
                        小计 {Number.isNaN(price) ? '—' : formatMoney(price, currency)}
                      </span>
                      <label className="review-stock">
                        <input
                          type="checkbox"
                          checked={d.is_stock_item}
                          onChange={(e) => updateDraft(i, { is_stock_item: e.target.checked })}
                        />
                        入库
                      </label>
                    </li>
                  )
                })}
              </ul>
              <div className="review-summary" aria-label="核对汇总">
                <span>
                  行小计合计 {formatMoney(linesSum, currency)}
                </span>
                <span>
                  小票总计 {formatMoney(detail.total_amount, currency)}
                </span>
                <span>
                  差异 {formatMoney(recon.diff, currency)}（{recon.pct}%）
                  {recon.withinThreshold ? ' · 在 2% 以内' : ' · 超出 2%，请核对'}
                </span>
              </div>
              {confirmError && (
                <p className="page-error" role="alert">
                  {confirmError}
                </p>
              )}
              <button
                type="button"
                className="btn btn-primary btn-lg"
                disabled={confirming || !recon.withinThreshold}
                onClick={() => void handleConfirm()}
              >
                {confirming ? '确认中…' : '确认入库记账'}
              </button>
              {!recon.withinThreshold && (
                <p className="page-note">差异超出 2% 时无法确认，请先核对各行金额。</p>
              )}
            </>
          ) : (
            <ul className="receipt-lines">
              {detail.lines.map((l) => (
                <li key={l.id} className="receipt-line-row">
                  <span className="receipt-line-name">
                    {l.canonical_name ?? l.raw_name}
                    {l.canonical_name && l.canonical_name !== l.raw_name ? (
                      <span className="receipt-line-raw">（{l.raw_name}）</span>
                    ) : null}
                  </span>
                  <span>
                    {l.quantity} {l.unit}
                  </span>
                  <span>{formatMoney(l.price, resolveCurrency(l.currency))}</span>
                  <span>{l.is_stock_item ? '入库' : '不入库'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <p>
        <Link to="/app/receipts">← 返回小票列表</Link>
      </p>
    </div>
  )
}
