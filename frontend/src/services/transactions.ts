/**
 * Transactions + spending summary API — Phase 2 design §5.1/§5.3/§5.4
 * (đối chiếu code backend app/api/transactions.py trên main @ 5f7f4fc).
 *
 * Response shapes (backend thật):
 * - GET /transactions?household_id&currency?&category?&from?&to?&limit=50&offset=0
 *   → `[transaction]` thuần, mới nhất trước (occurred_at DESC, created_at DESC, id DESC).
 * - POST /transactions `{household_id, type, amount (gt=0), currency, category,
 *   occurred_at, note?}` → 201. `receipt_id` KHÔNG nhận từ client
 *   (extra="forbid" — gửi lên là 422); chỉ worker/confirm tạo transaction có receipt.
 * - PATCH / DELETE /transactions/{id} `{amount? (gt=0), category?, note?, occurred_at?}`
 *   → chỉ khi `receipt_id IS NULL`; transaction từ hoá đơn → 409.
 * - GET /spending/summary?household_id&currency&from?&to?&group_by?= → 
 *   `{currency, total, by_category: [{category, total}], by_month: [{month, total}]}`.
 *   `currency` BẮT BUỘC (thiếu → 400). Chỉ tính type='expense'. `group_by`
 *   được validate nhưng KHÔNG lọc response — response luôn mang cả hai nhóm.
 *
 * D-F7 ĐÃ GIẢI QUYẾT (P2-06, 2026-11-21): backend `CURRENCIES` mở rộng
 * thành 14 tiền tệ (CNY, VND, USD, EUR, HKD, THB, MYR, SGD, IDR, PHP, KHR,
 * LAK, MMK, BND) — xem design doc §10.2. Client offer đủ 14, không cộng
 * trộn tiền tệ: summary vẫn tính riêng từng tiền tệ, không quy đổi.
 */
import { request } from './http'
import { SUPPORTED_CURRENCIES, type Currency } from '../utils/format'

export type TransactionType = 'expense' | 'income'
export type TransactionCategory = 'food' | 'household' | 'maintenance' | 'other'

/**
 * 14 tiền tệ backend chấp nhận (app/api/transactions.py: CURRENCIES, P2-06).
 * Thứ tự + nội dung lấy từ SUPPORTED_CURRENCIES (utils/format.ts) — một
 * nguồn duy nhất, không liệt kê lại ở đây.
 */
export const TRANSACTION_CURRENCIES: readonly Currency[] = SUPPORTED_CURRENCIES

export const TRANSACTION_CATEGORIES: readonly TransactionCategory[] = [
  'food',
  'household',
  'maintenance',
  'other',
]

/** Nhãn zh-CN cho 4 category của backend — UI label, không phải giá trị API. */
export const CATEGORY_LABELS: Record<TransactionCategory, string> = {
  food: '餐饮',
  household: '日用',
  maintenance: '维修保养',
  other: '其他',
}

/** Nhãn zh-CN cho tiền tệ trong selector (ký hiệu ¥/₫ lấy từ format.ts). */
export const CURRENCY_LABELS: Record<Currency, string> = {
  CNY: '人民币',
  VND: '越南盾',
  USD: '美元',
  EUR: '欧元',
  HKD: '港元',
  THB: '泰铢',
  MYR: '马来西亚林吉特',
  SGD: '新加坡元',
  IDR: '印度尼西亚盾',
  PHP: '菲律宾比索',
  KHR: '柬埔寨瑞尔',
  LAK: '老挝基普',
  MMK: '缅甸元',
  BND: '文莱元',
}

export const TYPE_LABELS: Record<TransactionType, string> = {
  expense: '支出',
  income: '收入',
}

export interface Transaction {
  id: string
  household_id: string
  /** null = chi tay (sửa/xoá được); uuid = chi từ hoá đơn (chỉ đọc, PATCH/DELETE → 409). */
  receipt_id: string | null
  type: TransactionType
  amount: number
  currency: Currency
  category: TransactionCategory
  occurred_at: string
  note: string | null
  created_at: string | null
  updated_at: string | null
}

/** Sổ chi tiêu thủ công chỉ tạo type='expense' — income không lộ ra ở form. */
export interface TransactionCreateInput {
  household_id: string
  type: 'expense'
  amount: number
  currency: Currency
  category: TransactionCategory
  occurred_at: string
  note?: string
}

export interface TransactionPatchInput {
  amount?: number
  category?: TransactionCategory
  note?: string | null
  occurred_at?: string
}

export interface CategoryTotal {
  category: TransactionCategory
  total: number
}

export interface MonthTotal {
  month: string
  total: number
}

export interface SpendingSummary {
  currency: Currency
  total: number
  by_category: CategoryTotal[]
  by_month: MonthTotal[]
}

/** Transaction từ hoá đơn thì chỉ đọc — UI không được hiện nút sửa/xoá cho nó. */
export function isManualTransaction(tx: Transaction): boolean {
  return tx.receipt_id === null
}

export function listTransactions(
  householdId: string,
  opts?: {
    currency?: Currency
    category?: TransactionCategory
    from?: string
    to?: string
    limit?: number
    offset?: number
  },
): Promise<Transaction[]> {
  const q = new URLSearchParams({
    household_id: householdId,
    limit: String(opts?.limit ?? 50),
    offset: String(opts?.offset ?? 0),
  })
  if (opts?.currency) q.set('currency', opts.currency)
  if (opts?.category) q.set('category', opts.category)
  if (opts?.from) q.set('from', opts.from)
  if (opts?.to) q.set('to', opts.to)
  return request<Transaction[]>(`/transactions?${q.toString()}`)
}

export function createTransaction(body: TransactionCreateInput): Promise<Transaction> {
  return request<Transaction>('/transactions', { method: 'POST', body })
}

export function patchTransaction(id: string, body: TransactionPatchInput): Promise<Transaction> {
  return request<Transaction>(`/transactions/${id}`, { method: 'PATCH', body })
}

export function deleteTransaction(id: string): Promise<void> {
  return request<void>(`/transactions/${id}`, { method: 'DELETE' })
}

export function getSpendingSummary(
  householdId: string,
  currency: Currency,
  opts?: { from?: string; to?: string; group_by?: 'category' | 'month' },
): Promise<SpendingSummary> {
  const q = new URLSearchParams({ household_id: householdId, currency })
  if (opts?.from) q.set('from', opts.from)
  if (opts?.to) q.set('to', opts.to)
  if (opts?.group_by) q.set('group_by', opts.group_by)
  return request<SpendingSummary>(`/spending/summary?${q.toString()}`)
}

/**
 * Validation ô số tiền ở form (client-side trước, server là thẩm quyền —
 * amount Decimal gt=0, NUMERIC(10,2)). Trả thông báo lỗi zh-CN hoặc null.
 */
export function validateAmountText(text: string): string | null {
  const t = text.trim()
  if (t === '') return '请输入金额'
  if (!/^-?\d+(\.\d+)?$/.test(t)) return '请输入正确的金额'
  if (!/^-?\d+(\.\d{1,2})?$/.test(t)) return '金额最多保留两位小数'
  if (Number(t) <= 0) return '金额必须大于 0'
  return null
}
