/**
 * Review draft store — Zustand client state (§8.7): sửa từng dòng trước
 * confirm (ephemeral; bỏ khi unmount màn Review).
 *
 * Mỗi dòng draft giữ `unitPrice` (đơn giá user sửa) — `price` gửi lên là
 * tiểu kế = round2(quantity × unitPrice) (xem utils/format.lineTotal và
 * ghi chú trong services/receipts.ts). Dòng thêm mới có `lineId: null`
 * (D-F3) và `clientKey` tạm để React key + undo.
 */
import { create } from 'zustand'
import { lineTotal, round2, unitPriceFromLine } from '../utils/format'
import { uuidv4 } from '../utils/uuid'
import type { ReceiptLine } from '../services/receipts'

export interface ReviewLineDraft {
  clientKey: string
  lineId: string | null
  lineNo: number
  rawName: string
  canonicalName: string | null
  quantity: number
  unit: string
  unitPrice: number
  isStockItem: boolean
  isNew: boolean
  /** Dòng giảm giá / phí: border trái riêng + không tính là stock (§5.3). */
  isDiscount: boolean
}

export function isDiscountLine(rawName: string): boolean {
  return /优惠|折扣|运费|服务费/.test(rawName)
}

export function draftFromLine(line: ReceiptLine): ReviewLineDraft {
  const discount = isDiscountLine(line.raw_name) || line.price < 0
  return {
    clientKey: line.id,
    lineId: line.id,
    lineNo: line.line_no,
    rawName: line.raw_name,
    canonicalName: line.canonical_name,
    quantity: line.quantity,
    unit: line.unit,
    unitPrice: unitPriceFromLine(line.price, line.quantity),
    isStockItem: line.is_stock_item,
    isNew: false,
    isDiscount: discount,
  }
}

export function newEmptyDraft(lineNo: number): ReviewLineDraft {
  return {
    clientKey: `new-${uuidv4()}`,
    lineId: null,
    lineNo,
    rawName: '',
    canonicalName: null,
    quantity: 1,
    unit: '个',
    unitPrice: 0,
    isStockItem: true,
    isNew: true,
    isDiscount: false,
  }
}

/** Tiểu kế của draft (số gửi lên làm `price`). */
export function draftLineTotal(draft: ReviewLineDraft): number {
  return lineTotal(draft.quantity, draft.unitPrice)
}

interface ReviewDraftState {
  receiptId: string | null
  lines: ReviewLineDraft[]
  /** Dòng vừa xóa (để undo trong 5s, §5.3). */
  lastRemoved: { draft: ReviewLineDraft; index: number } | null
  init: (receiptId: string, lines: ReceiptLine[]) => void
  updateLine: (clientKey: string, patch: Partial<ReviewLineDraft>) => void
  addLine: () => void
  removeLine: (clientKey: string) => void
  undoRemove: () => void
  /** Ẩn thanh undo sau 5s (§5.3) — không xóa draft. */
  dismissRemoved: () => void
  clear: () => void
}

export const useReviewDraftStore = create<ReviewDraftState>()((set, get) => ({
  receiptId: null,
  lines: [],
  lastRemoved: null,
  init: (receiptId, lines) =>
    set({ receiptId, lines: lines.map(draftFromLine), lastRemoved: null }),
  updateLine: (clientKey, patch) =>
    set((s) => ({
      lines: s.lines.map((l) => {
        if (l.clientKey !== clientKey) return l
        const next = { ...l, ...patch }
        // Đổi tên hoặc đơn giá → tính lại isDiscount (dòng có giá âm là
        // dòng giảm giá/phí, §5.3) và tự tắt is_stock_item.
        if (patch.rawName !== undefined || patch.unitPrice !== undefined) {
          next.isDiscount = isDiscountLine(next.rawName) || draftLineTotal(next) < 0
          if (next.isDiscount) next.isStockItem = false
        }
        return next
      }),
    })),
  addLine: () =>
    set((s) => ({
      lines: [...s.lines, newEmptyDraft(s.lines.length + 1)],
    })),
  removeLine: (clientKey) => {
    const { lines } = get()
    const index = lines.findIndex((l) => l.clientKey === clientKey)
    if (index < 0) return
    set({ lines: lines.filter((l) => l.clientKey !== clientKey), lastRemoved: { draft: lines[index], index } })
  },
  undoRemove: () => {
    const { lastRemoved, lines } = get()
    if (!lastRemoved) return
    const next = [...lines]
    next.splice(Math.min(lastRemoved.index, next.length), 0, lastRemoved.draft)
    set({ lines: next, lastRemoved: null })
  },
  dismissRemoved: () => set({ lastRemoved: null }),
  clear: () => set({ receiptId: null, lines: [], lastRemoved: null }),
}))

/** Tổng tiểu kế hiện tại của toàn bộ draft (live summary bar, §5.3). */
export function reviewLinesSum(lines: ReviewLineDraft[]): number {
  return round2(lines.reduce((sum, l) => sum + draftLineTotal(l), 0))
}
