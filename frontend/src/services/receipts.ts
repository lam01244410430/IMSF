/**
 * Receipts API — design doc §8.4/§8.5 + Phase 1 API §5.1 (đối chiếu code
 * backend app/api/receipts.py trên main @ be97baf).
 *
 * Response shapes (backend thật):
 * - POST /receipts → 202 `{id, status: "pending"}` (idempotent re-POST cùng
 *   key trong 24h trả receipt đã tạo).
 * - GET /receipts?household_id&status?&limit=20&offset=0 → `[receipt]`
 *   (không kèm lines).
 * - GET /receipts/{id} → receipt + `lines: [receipt_line]` +
 *   `inventory_created: n`.
 * - POST /receipts/{id}/confirm `{lines: [{line_id, quantity, unit, price,
 *   is_stock_item}]}` → receipt detail mới (200); 409 khi không còn
 *   needs_review; 422 khi line không hợp lệ.
 * - GET /receipts/{id}/image → ảnh gốc (cần auth).
 *
 * LƯU Ý QUAN TRỌNG — `price` trong receipt_line và trong payload confirm là
 * TỔNG TIỀN CỦA DÒNG (tiểu kế), KHÔNG phải đơn giá: backend đối soát bằng
 * SUM(price) (Phase 1 §6.4, app/reconcile.py). UI sửa "đơn giá" thì client
 * phải gửi `price = round2(quantity × unitPrice)` — xem utils/format.lineTotal.
 */
import { useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { useQuery } from '@tanstack/react-query'
import { apiUrl } from '../config/env'
import { ApiError, apiErrorToZh } from './errors'
import { getAccessToken } from './auth'
import { request } from './http'

export type ReceiptStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'needs_review'

export const TERMINAL_STATUSES: readonly ReceiptStatus[] = ['completed', 'failed', 'needs_review']

export function isTerminalStatus(status: ReceiptStatus): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status)
}

export interface ReceiptLine {
  id: string
  line_no: number
  raw_name: string
  quantity: number
  unit: string
  /** Tiểu kế của dòng (không phải đơn giá) — xem ghi chú đầu file. */
  price: number
  currency: string
  canonical_ingredient_id: string | null
  canonical_name: string | null
  is_stock_item: boolean
}

export interface Receipt {
  id: string
  household_id: string
  uploaded_by_user_id: string | null
  image_url: string
  store_name: string | null
  purchased_at: string | null
  total_amount: number
  currency: string
  status: ReceiptStatus
  ocr_raw_text: string | null
  error_message: string | null
  processed_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ReceiptDetail extends Receipt {
  lines: ReceiptLine[]
  inventory_created: number
}

export interface ConfirmLineInput {
  /**
   * D-F3 (doc §10.2, task Phase B): dòng client thêm gửi `line_id: null`
   * theo đề xuất của design doc. Backend hiện tại (ConfirmLine.line_id:
   * uuid.UUID bắt buộc + kiểm tra line thuộc receipt, 422 nếu không) CHƯA
   * chấp nhận null — confirm có dòng thêm sẽ 422 cho tới khi backend xác
   * nhận/đổi shape. Client vẫn gửi null theo chỉ đạo, không tự bịa UUID.
   */
  line_id: string | null
  quantity: number
  unit: string
  /** Tiểu kế của dòng (không phải đơn giá). */
  price: number
  is_stock_item: boolean
}

export function listReceipts(
  householdId: string,
  opts?: { status?: ReceiptStatus; limit?: number; offset?: number },
): Promise<Receipt[]> {
  const q = new URLSearchParams({
    household_id: householdId,
    limit: String(opts?.limit ?? 20),
    offset: String(opts?.offset ?? 0),
  })
  if (opts?.status) q.set('status', opts.status)
  return request<Receipt[]>(`/receipts?${q.toString()}`)
}

export function getReceipt(id: string): Promise<ReceiptDetail> {
  return request<ReceiptDetail>(`/receipts/${id}`)
}

export function confirmReceipt(id: string, lines: ConfirmLineInput[]): Promise<ReceiptDetail> {
  return request<ReceiptDetail>(`/receipts/${id}/confirm`, {
    method: 'POST',
    body: { lines },
  })
}

/**
 * Ảnh gốc — endpoint cần auth nên không dùng URL trần làm src.
 * weapp: Taro.downloadFile (header Authorization) → tempFilePath.
 * H5: Taro.request arraybuffer → Blob URL.
 * (Branch TARO_ENV được phép trong src/services/** — lint rule §8.2.)
 */
export async function fetchReceiptImageSrc(id: string): Promise<string> {
  const url = apiUrl(`/receipts/${id}/image`)
  const token = getAccessToken()
  const authorization = `Bearer ${token}`
  if (process.env.TARO_ENV === 'weapp') {
    const res = await Taro.downloadFile({ url, header: { Authorization: authorization } })
    if (res.statusCode !== 200) {
      throw new ApiError(res.statusCode, apiErrorToZh(res.statusCode))
    }
    return res.tempFilePath
  }
  const res = await Taro.request({
    url,
    header: { Authorization: authorization },
    responseType: 'arraybuffer',
    timeout: 30_000,
  })
  if (res.statusCode !== 200) {
    throw new ApiError(res.statusCode, apiErrorToZh(res.statusCode))
  }
  const blob = new Blob([res.data as ArrayBuffer], { type: 'image/jpeg' })
  return URL.createObjectURL(blob)
}

// --- Polling (§8.5) -------------------------------------------------------
export const RECEIPT_POLL_FIRST_MS = 3_000
export const RECEIPT_POLL_LATER_MS = 5_000
export const RECEIPT_POLL_FAST_WINDOW_MS = 60_000
export const RECEIPT_POLL_SOFT_TIMEOUT_MS = 180_000
export const RECEIPT_POLL_HARD_TIMEOUT_MS = 300_000

/** Nhịp poll theo thời gian đã trôi: 3s trong 60s đầu, rồi 5s. */
export function pollIntervalFor(elapsedMs: number, status: ReceiptStatus | undefined): number | false {
  if (!status || isTerminalStatus(status)) return false
  if (elapsedMs >= RECEIPT_POLL_HARD_TIMEOUT_MS) return false
  return elapsedMs < RECEIPT_POLL_FAST_WINDOW_MS ? RECEIPT_POLL_FIRST_MS : RECEIPT_POLL_LATER_MS
}

/**
 * Poll GET /receipts/{id} bằng TanStack Query `refetchInterval` (§8.5) —
 * không setInterval hand-rolled. Trả kèm đồng hồ elapsed (cập nhật mỗi giây)
 * và cờ soft/hard timeout (§5.2).
 */
export function useReceiptPolling(receiptId: string | null, opts?: { enabled?: boolean }) {
  const enabled = !!receiptId && opts?.enabled !== false
  const startedAtRef = useRef<number>(Date.now())
  const [elapsedMs, setElapsedMs] = useState(0)

  useEffect(() => {
    startedAtRef.current = Date.now()
    setElapsedMs(0)
  }, [receiptId])

  useEffect(() => {
    if (!enabled) return
    const timer = setInterval(() => setElapsedMs(Date.now() - startedAtRef.current), 1000)
    return () => clearInterval(timer)
  }, [enabled])

  const query = useQuery({
    queryKey: ['receipt', receiptId],
    queryFn: () => getReceipt(receiptId as string),
    enabled,
    refetchInterval: (q) => {
      const data = q.state.data as ReceiptDetail | undefined
      return pollIntervalFor(Date.now() - startedAtRef.current, data?.status)
    },
  })

  const status = query.data?.status
  const terminal = !!status && isTerminalStatus(status)
  return {
    ...query,
    elapsedMs,
    isSoftTimeout: !terminal && elapsedMs >= RECEIPT_POLL_SOFT_TIMEOUT_MS,
    isHardTimeout: !terminal && elapsedMs >= RECEIPT_POLL_HARD_TIMEOUT_MS,
  }
}
