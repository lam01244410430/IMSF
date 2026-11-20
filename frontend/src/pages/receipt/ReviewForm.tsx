/**
 * ReviewForm — Màn 03 需要核对 (§5.3): image card + mismatch card + line
 * editor + live summary + action bar + confirm (200/409/422).
 *
 * 重新识别 ẨN (D-F2 — backend không có endpoint reprocess, §10.2).
 * Dòng thêm gửi line_id: null (D-F3) — backend hiện tại 422 cho tới khi
 * xác nhận/đổi shape (xem services/receipts.ts).
 * Input tên chuẩn cho dòng 未匹配 là display-only: ConfirmLine không có
 * field canonical_name nên tên gõ vào không gửi lên được (chờ backend).
 */
import { useCallback, useEffect, useState } from 'react'
import { Image, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import Skeleton from '../../ui/primitives/Skeleton'
import { useReceiptImage } from './useReceiptImage'
import LineCard, { type LineFieldErrors } from './LineCard'
import {
  confirmReceipt,
  type ReceiptDetail,
} from '../../services/receipts'
import {
  draftLineTotal,
  reviewLinesSum,
  useReviewDraftStore,
  type ReviewLineDraft,
} from '../../store/reviewDraft'
import { ApiError } from '../../services/errors'
import { showToast } from '../../ui/primitives/Toast'
import { formatMoney, reconciliationDiff, withAlpha } from '../../utils/format'
import { goFridge, goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'

export interface ReviewFormProps {
  detail: ReceiptDetail
  /** Refetch GET detail của trang cha (dùng cho 409 + chuyển trạng thái). */
  refetch: () => void
}

function safeAreaBottom(): number {
  try {
    const info = Taro.getSystemInfoSync()
    const bottom = info.safeArea?.bottom ?? info.windowHeight ?? 0
    return Math.max(0, (info.windowHeight ?? 0) - bottom)
  } catch {
    return 0
  }
}

/** Map lỗi 422 FastAPI (loc body/lines/i/field) về slot inline (§5.3). */
function map422Errors(
  e: ApiError,
  lines: ReviewLineDraft[],
): { errors: Record<string, LineFieldErrors>; count: number } {
  const detail = (e.data as { detail?: unknown } | undefined)?.detail
  const errors: Record<string, LineFieldErrors> = {}
  let count = 0
  if (!Array.isArray(detail)) return { errors, count }
  for (const item of detail) {
    const loc = (item as { loc?: unknown })?.loc
    if (!Array.isArray(loc) || loc[0] !== 'body' || loc[1] !== 'lines') continue
    const idx = loc[2]
    const field = loc[3]
    if (typeof idx !== 'number' || typeof field !== 'string') continue
    const line = lines[idx]
    if (!line) continue
    const slot = (errors[line.clientKey] ??= {})
    if (field === 'quantity' && !slot.quantity) {
      slot.quantity = '数量必须大于 0'
      count++
    } else if (field === 'unit' && !slot.unit) {
      slot.unit = '请选择单位'
      count++
    } else if (field === 'price' && !slot.unitPrice) {
      slot.unitPrice = '金额最多保留两位小数'
      count++
    }
  }
  return { errors, count }
}

export default function ReviewForm({ detail, refetch }: ReviewFormProps) {
  const imageQuery = useReceiptImage(detail.id)
  const imageSrc = imageQuery.data
  const lines = useReviewDraftStore((s) => s.lines)
  const lastRemoved = useReviewDraftStore((s) => s.lastRemoved)
  const [detailOverride, setDetailOverride] = useState<ReceiptDetail | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, LineFieldErrors>>({})
  const [submitted, setSubmitted] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState<{ detail: ReceiptDetail; sum: number } | null>(null)

  const currentDetail = detailOverride ?? detail
  const totalAmount = currentDetail.total_amount
  const currency = currentDetail.currency === 'VND' ? 'VND' : 'CNY'
  const linesSum = reviewLinesSum(lines)
  const diffInfo = reconciliationDiff(totalAmount, linesSum)
  const unmappedCount = lines.filter((l) => !l.canonicalName).length

  // Init draft một lần cho mỗi receipt — KHÔNG reset khi refetch (mất sửa
  // là kết quả tệ nhất trên màn này, §5.3).
  useEffect(() => {
    if (useReviewDraftStore.getState().receiptId !== detail.id) {
      useReviewDraftStore.getState().init(detail.id, detail.lines)
    }
  }, [detail.id, detail.lines])
  // Draft là ephemeral — bỏ khi unmount màn Review (§8.7).
  useEffect(() => () => useReviewDraftStore.getState().clear(), [])

  // Thanh undo tự ẩn sau 5s (§5.3).
  useEffect(() => {
    if (!lastRemoved) return
    const t = setTimeout(() => useReviewDraftStore.getState().dismissRemoved(), 5000)
    return () => clearTimeout(t)
  }, [lastRemoved])

  const handleErrorsChange = useCallback((clientKey: string, errors: LineFieldErrors) => {
    setFieldErrors((prev) => {
      const next = { ...prev }
      if (Object.keys(errors).length === 0) delete next[clientKey]
      else next[clientKey] = errors
      return next
    })
  }, [])

  const handleRemove = (clientKey: string) => {
    if (lines.length <= 1) {
      showToast('至少保留一行明细', 'error')
      return
    }
    useReviewDraftStore.getState().removeLine(clientKey)
    setFieldErrors((prev) => {
      const next = { ...prev }
      delete next[clientKey]
      return next
    })
  }

  const handleConfirm = async () => {
    setSubmitted(true)
    if (lines.length === 0) {
      showToast('至少保留一行明细', 'error')
      return
    }
    const errorEntries = Object.entries(fieldErrors).filter(([, e]) => Object.keys(e).length > 0)
    const totalErrors = errorEntries.reduce((n, [, e]) => n + Object.keys(e).length, 0)
    if (totalErrors > 0) {
      const firstKey = errorEntries[0][0]
      Taro.pageScrollTo({ selector: `#line-${firstKey}`, duration: 300 })
      showToast(`有 ${totalErrors} 项需要修改，请检查标红处`, 'error')
      return
    }
    const payload = lines.map((l) => ({
      line_id: l.lineId,
      quantity: l.quantity,
      unit: l.unit,
      price: draftLineTotal(l),
      is_stock_item: l.isStockItem,
    }))
    const sentSum = reviewLinesSum(lines)
    setConfirming(true)
    try {
      const res = await confirmReceipt(detail.id, payload)
      if (res.status === 'completed') {
        setConfirmed({ detail: res, sum: sentSum })
      } else if (res.status === 'needs_review') {
        setDetailOverride(res)
        showToast('仍有差额，请继续核对', 'info')
      } else {
        // Trạng thái khác (processing/pending) — để trang cha render theo
        // trạng thái thật (refetch GET).
        refetch()
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        refetch()
        showToast('小票状态已更新，请查看最新结果', 'info')
      } else if (e instanceof ApiError && e.status === 422) {
        const mapped = map422Errors(e, lines)
        if (mapped.count > 0) {
          setFieldErrors((prev) => ({ ...prev, ...mapped.errors }))
          const firstKey = Object.keys(mapped.errors)[0]
          Taro.pageScrollTo({ selector: `#line-${firstKey}`, duration: 300 })
          showToast(`有 ${mapped.count} 项需要修改，请检查标红处`, 'error')
        } else {
          showToast(e.messageZh, 'error')
        }
      } else if (e instanceof ApiError) {
        showToast(e.messageZh, 'error')
      } else {
        showToast('网络异常，请检查网络后重试', 'error')
      }
    } finally {
      setConfirming(false)
    }
  }

  // --- Success sau confirm (200 → completed, §5.3) --------------------------
  if (confirmed) {
    return (
      <View
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          padding: 32,
          paddingTop: 48,
        }}
      >
        <View
          style={{
            width: 64,
            height: 64,
            borderRadius: 32,
            backgroundColor: tokens.color.primaryContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Text style={{ fontSize: 28, color: tokens.color.primary }}>✓</Text>
        </View>
        <Text style={{ fontSize: 18, fontWeight: 700, color: tokens.color.onSurface }}>已确认并入库</Text>
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>
          {confirmed.detail.inventory_created} 件食材已记入冰箱
        </Text>
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>
          记账 {formatMoney(confirmed.sum, currency)}
        </Text>
        <View style={{ marginTop: 8, width: '100%' }}>
          <Button variant='primary' size='large' block onClick={() => void goFridge()}>
            查看冰箱
          </Button>
        </View>
        <Button variant='ghost' onClick={() => void goUpload()}>
          返回首页
        </Button>
      </View>
    )
  }

  const showMismatchCard = !diffInfo.withinThreshold
  const showUnmappedCard = diffInfo.withinThreshold && unmappedCount > 0

  return (
    <View style={{ paddingBottom: 170 + safeAreaBottom() }}>
      {/* Receipt image card */}
      <View style={{ padding: 16, paddingBottom: 0 }}>
        {imageQuery.isLoading ? (
          <Skeleton variant='block' width='100%' height={240} />
        ) : imageSrc ? (
          <View
            onClick={() => void Taro.previewImage({ current: imageSrc, urls: [imageSrc] })}
            style={{ borderRadius: tokens.shape.card, overflow: 'hidden' }}
          >
            <Image
              src={imageSrc}
              mode='widthFix'
              style={{ width: '100%', maxHeight: 240, borderRadius: tokens.shape.card }}
            />
          </View>
        ) : (
          <View
            style={{
              height: 240,
              borderRadius: tokens.shape.card,
              backgroundColor: tokens.color.surfaceVariant,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>图片加载失败</Text>
          </View>
        )}
        <Text
          style={{
            fontSize: 13,
            color: tokens.color.onSurfaceVariant,
            textAlign: 'center',
            marginTop: 8,
          }}
        >
          点按图片可放大查看
        </Text>
      </View>

      {/* Mismatch / unmapped explanation card */}
      {showMismatchCard || showUnmappedCard ? (
        <View style={{ padding: 16, paddingBottom: 0 }}>
          <View
            style={{
              backgroundColor: tokens.color.warningContainer,
              borderWidth: 1,
              borderStyle: 'solid',
              borderColor: withAlpha(tokens.color.warning, 0.4),
              borderRadius: tokens.shape.base,
              padding: 12,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Icon name='warning' size={16} color={tokens.color.warning} />
              <Text style={{ fontSize: 15, fontWeight: 600, color: tokens.color.onSurface }}>
                {showMismatchCard ? '总价对不上，需要您核对' : `有 ${unmappedCount} 行商品未能识别，请确认或修改。`}
              </Text>
            </View>
            {showMismatchCard ? (
              <>
                <Text style={{ fontSize: 13, color: tokens.color.onSurface }}>
                  小票总价 {formatMoney(totalAmount, currency)}，明细合计 {formatMoney(linesSum, currency)}
                  ，相差 {formatMoney(diffInfo.diff, currency)}（约 {diffInfo.pct.toFixed(1)}%）。超过 2%
                  的误差不会自动入库，请修改明细或重新识别。
                </Text>
                <View style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <View style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>小票总价</Text>
                    <Text style={{ fontSize: 13, color: tokens.color.onSurface }}>
                      {formatMoney(totalAmount, currency)}
                    </Text>
                  </View>
                  <View style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>明细合计</Text>
                    <Text style={{ fontSize: 13, color: tokens.color.onSurface }}>
                      {formatMoney(linesSum, currency)}
                    </Text>
                  </View>
                  <View style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>相差</Text>
                    <Text style={{ fontSize: 13, color: tokens.color.onSurface }}>
                      {formatMoney(diffInfo.diff, currency)} ({diffInfo.pct.toFixed(1)}%)
                    </Text>
                  </View>
                </View>
              </>
            ) : null}
          </View>
        </View>
      ) : null}

      {/* Line list */}
      <View
        style={{
          padding: 16,
          paddingBottom: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {lines.map((line) => (
          <LineCard
            key={line.clientKey}
            draft={line}
            currency={currency}
            forceShowErrors={submitted}
            errors={fieldErrors[line.clientKey] ?? {}}
            onErrorsChange={handleErrorsChange}
            onRemove={handleRemove}
            canRemove={lines.length > 1}
          />
        ))}

        <View
          style={{
            height: 48,
            borderWidth: 1.5,
            borderStyle: 'dashed',
            borderColor: tokens.color.primary,
            borderRadius: tokens.shape.base,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onClick={() => useReviewDraftStore.getState().addLine()}
        >
          <Text style={{ fontSize: 15, color: tokens.color.primary }}>＋ 添加一行</Text>
        </View>
      </View>

      {/* Action bar cố định: undo (nếu có) + live summary + 确认并入库 */}
      <View
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          backgroundColor: tokens.color.surface,
          borderTopWidth: 1,
          borderTopStyle: 'solid',
          borderTopColor: tokens.color.divider,
          padding: 12,
          paddingBottom: 12 + safeAreaBottom(),
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: tokens.zIndex.bottomNavigation,
        }}
      >
        {lastRemoved ? (
          <View
            style={{
              backgroundColor: tokens.color.surfaceVariant,
              borderRadius: tokens.shape.base,
              padding: 10,
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>已删除 1 行</Text>
            <Text
              style={{ fontSize: 14, fontWeight: 600, color: tokens.color.primary }}
              onClick={() => useReviewDraftStore.getState().undoRemove()}
            >
              撤销
            </Text>
          </View>
        ) : null}
        <View style={{ display: 'flex', flexDirection: 'row', justifyContent: 'center' }}>
          {diffInfo.withinThreshold ? (
            <Text style={{ fontSize: 14, fontWeight: 600, color: tokens.color.primary }}>
              ✓ 已对上，相差 {formatMoney(diffInfo.diff, currency)}
            </Text>
          ) : (
            <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>
              明细合计 {formatMoney(linesSum, currency)} · 相差 {formatMoney(diffInfo.diff, currency)} (
              {diffInfo.pct.toFixed(1)}%)
            </Text>
          )}
        </View>
        <Button variant='primary' size='large' block loading={confirming} onClick={() => void handleConfirm()}>
          确认并入库
        </Button>
      </View>
    </View>
  )
}
