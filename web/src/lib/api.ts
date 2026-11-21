/**
 * Typed API client for the app pages — thin wrappers over the foundation
 * auth client (`lib/auth.ts`: same-origin /api/v2/..., single-flight
 * refresh). Response shapes verified against the live backend code
 * (app/api/*.py on main) and the Taro services, because the OpenAPI
 * responses are untyped (`{}`).
 *
 * - GET /transactions → `[transaction]`, newest first.
 * - POST /transactions `{household_id, type, amount (gt=0), currency,
 *   category, occurred_at, note?}` → 201. `receipt_id` is NOT accepted
 *   from the client (extra="forbid" → 422).
 * - PATCH/DELETE /transactions/{id} → only when `receipt_id IS NULL`;
 *   receipt-linked rows → 409 (the UI hides the buttons for them).
 * - GET /spending/summary?household_id&currency (REQUIRED, missing →
 *   400) → `{currency, total, by_category: [{category, total}],
 *   by_month: [{month, total}]}`. Expense-only, ONE currency at a time.
 * - GET /fridge?household_id → `[inventory item]` with `days_left`
 *   (auto_expiry_date − today in the household timezone; null when no
 *   expiry date). POST /fridge/{id}/consume (no body);
 *   POST /fridge/{id}/extend `{days}` (default 3).
 * - GET /receipts?household_id → `[receipt]` (no lines);
 *   GET /receipts/{id} → receipt + `lines` + `inventory_created`;
 *   POST /receipts/{id}/confirm `{lines: [{line_id, quantity, unit,
 *   price, is_stock_item}]}` → 200; 409 when no longer needs_review;
 *   422 for an invalid line. NOTE (D-F3): `line_id` must be a UUID of a
 *   line belonging to the receipt — the backend does NOT accept
 *   client-added lines, so the review UI offers no add-line control.
 * - GET /equipments?household_id → `[equipment]` with
 *   `next_maintenance_date` + `days_until_maintenance`;
 *   GET /equipments/{id}/maintenance → history, newest first;
 *   POST /equipments/{id}/maintenance `{performed_at,
 *   maintenance_type, note?, cost?, currency?}` → `{log, equipment,
 *   transaction}` (`transaction` null when no cost; cost=0 logs cost 0
 *   with NO ledger row — transactions.amount has a CHECK > 0).
 * - GET /notifications?household_id → newest first; POST
 *   /notifications/{id}/respond `{response: 'used_up' | 'extended',
 *   days?}` — only open lazy_tracking notifications, else 409. There
 *   is NO mark-as-read endpoint: the bell tracks "seen" client-side
 *   in localStorage (see NotificationsBell).
 * - GET /households → `[{id, name, default_currency, timezone, locale,
 *   created_at, role}]`.
 */
import { apiFetch, apiGetJson } from './auth'
import type { Currency } from './format'

export type TransactionType = 'expense' | 'income'
export type TransactionCategory = 'food' | 'household' | 'maintenance' | 'other'

export const TRANSACTION_CATEGORIES: readonly TransactionCategory[] = [
  'food',
  'household',
  'maintenance',
  'other',
]

/** zh-CN labels for the 4 backend categories — UI labels, not API values. */
export const CATEGORY_LABELS: Record<TransactionCategory, string> = {
  food: '餐饮',
  household: '日用',
  maintenance: '维修保养',
  other: '其他',
}

export const TYPE_LABELS: Record<TransactionType, string> = {
  expense: '支出',
  income: '收入',
}

export interface Household {
  id: string
  name: string
  default_currency: string
  timezone: string
  locale: string
  created_at: string | null
  role: string
}

export interface Transaction {
  id: string
  household_id: string
  /** null = manual row (editable/deletable); uuid = from a receipt (read-only). */
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

/** The expense book only creates type='expense' — income is not in the form. */
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

/** A receipt-linked transaction is read-only — the UI must not show edit/delete for it. */
export function isManualTransaction(tx: Transaction): boolean {
  return tx.receipt_id === null
}

export interface FridgeItem {
  id: string
  household_id: string
  receipt_id: string | null
  receipt_line_id: string | null
  raw_name: string
  canonical_ingredient_id: string | null
  quantity: number
  unit: string
  price: number | null
  currency: string
  storage_zone: string
  added_date: string | null
  auto_expiry_date: string | null
  status: 'fresh' | 'expiring' | 'expired' | 'consumed'
  consumed_at: string | null
  created_at: string | null
  updated_at: string | null
  canonical_name: string | null
  /** Days until expiry (negative = expired); null when no expiry date. */
  days_left: number | null
}

export type ReceiptStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'needs_review'

export const RECEIPT_STATUS_LABELS: Record<ReceiptStatus, string> = {
  pending: '待处理',
  processing: '识别中',
  completed: '已完成',
  failed: '识别失败',
  needs_review: '待核对',
}

export interface ReceiptLine {
  id: string
  line_no: number
  raw_name: string
  quantity: number
  unit: string
  /** Line subtotal (not unit price) — backend reconciles SUM(price). */
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
  line_id: string
  quantity: number
  unit: string
  /** Line subtotal (not unit price). */
  price: number
  is_stock_item: boolean
}

export type MaintenanceType = 'cleaning' | 'filter_replace' | 'repair' | 'inspection'

export const MAINTENANCE_TYPE_LABELS: Record<MaintenanceType, string> = {
  cleaning: '清洁',
  filter_replace: '更换滤芯',
  repair: '维修',
  inspection: '检查',
}

export interface Equipment {
  id: string
  household_id: string
  type: string
  name: string | null
  device_type: string
  brand_model: string | null
  usage_intensity: string | null
  last_maintained_at: string | null
  next_maintenance_date: string | null
  rag_maintenance_notes: string | null
  status: string
  household_size: number | null
  usage_per_week: number | null
  maintenance_interval_days: number | null
  created_at: string | null
  updated_at: string | null
  days_until_maintenance: number | null
}

export interface MaintenanceLog {
  id: string
  equipment_id: string
  performed_at: string | null
  maintenance_type: MaintenanceType
  note: string | null
  cost: number | null
  currency: string | null
  transaction_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface MaintenanceCreateInput {
  performed_at: string
  maintenance_type: MaintenanceType
  note?: string | null
  cost?: number | null
  currency?: string | null
}

export interface MaintenanceCreateResult {
  log: MaintenanceLog
  equipment: Equipment
  transaction: Transaction | null
}

export type NotificationType = 'expiry_reminder' | 'lazy_tracking' | 'maintenance_reminder' | 'system'
export type NotificationStatus = 'sent' | 'delivered' | 'read' | 'responded' | 'failed'

export interface AppNotification {
  id: string
  user_id: string
  household_id: string
  type: NotificationType
  ref_type: string
  ref_id: string | null
  channel: string
  payload_json: Record<string, unknown> | null
  status: NotificationStatus
  response: string | null
  sent_at: string | null
  responded_at: string | null
  created_at: string | null
}

/** Open = can still be responded to (sent/delivered/read). */
export function isOpenNotification(n: AppNotification): boolean {
  return n.status === 'sent' || n.status === 'delivered' || n.status === 'read'
}

/** The notification text the backend stored (payload.message / title). */
export function notificationText(n: AppNotification): string {
  const p = n.payload_json ?? {}
  const message = typeof p.message === 'string' ? p.message : ''
  const title = typeof p.title === 'string' ? p.title : ''
  if (message) return message
  if (title) return title
  if (n.type === 'lazy_tracking') return '食材快过期了，请确认是否已用完。'
  if (n.type === 'expiry_reminder') return '有食材即将过期。'
  if (n.type === 'maintenance_reminder') return '有设备需要保养。'
  return '系统通知'
}

// ---------------------------------------------------------------------------
// Households
// ---------------------------------------------------------------------------

export function listHouseholds(): Promise<Household[]> {
  return apiGetJson<Household[]>('/api/v2/households')
}

// ---------------------------------------------------------------------------
// Transactions + spending
// ---------------------------------------------------------------------------

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
  return apiGetJson<Transaction[]>(`/api/v2/transactions?${q.toString()}`)
}

export async function createTransaction(body: TransactionCreateInput): Promise<Transaction> {
  const res = await apiFetch('/api/v2/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
  return (await res.json()) as Transaction
}

export async function patchTransaction(
  id: string,
  body: TransactionPatchInput,
): Promise<Transaction> {
  const res = await apiFetch(`/api/v2/transactions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
  return (await res.json()) as Transaction
}

export async function deleteTransaction(id: string): Promise<void> {
  const res = await apiFetch(`/api/v2/transactions/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
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
  return apiGetJson<SpendingSummary>(`/api/v2/spending/summary?${q.toString()}`)
}

// ---------------------------------------------------------------------------
// Fridge
// ---------------------------------------------------------------------------

export function listFridge(householdId: string, limit = 50): Promise<FridgeItem[]> {
  const q = new URLSearchParams({
    household_id: householdId,
    limit: String(limit),
    offset: '0',
  })
  return apiGetJson<FridgeItem[]>(`/api/v2/fridge?${q.toString()}`)
}

export async function consumeFridgeItem(itemId: string): Promise<FridgeItem> {
  const res = await apiFetch(`/api/v2/fridge/${itemId}/consume`, { method: 'POST' })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
  return (await res.json()) as FridgeItem
}

export async function extendFridgeItem(itemId: string, days = 3): Promise<FridgeItem> {
  const res = await apiFetch(`/api/v2/fridge/${itemId}/extend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ days }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
  return (await res.json()) as FridgeItem
}

// ---------------------------------------------------------------------------
// Receipts
// ---------------------------------------------------------------------------

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
  return apiGetJson<Receipt[]>(`/api/v2/receipts?${q.toString()}`)
}

export function getReceipt(id: string): Promise<ReceiptDetail> {
  return apiGetJson<ReceiptDetail>(`/api/v2/receipts/${id}`)
}

export async function confirmReceipt(id: string, lines: ConfirmLineInput[]): Promise<ReceiptDetail> {
  const res = await apiFetch(`/api/v2/receipts/${id}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    const err = new Error(
      typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`,
    ) as Error & { status?: number }
    err.status = res.status
    throw err
  }
  return (await res.json()) as ReceiptDetail
}

// ---------------------------------------------------------------------------
// Equipments + maintenance
// ---------------------------------------------------------------------------

export function listEquipments(householdId: string): Promise<Equipment[]> {
  const q = new URLSearchParams({ household_id: householdId })
  return apiGetJson<Equipment[]>(`/api/v2/equipments?${q.toString()}`)
}

export function getMaintenanceHistory(equipmentId: string): Promise<MaintenanceLog[]> {
  return apiGetJson<MaintenanceLog[]>(`/api/v2/equipments/${equipmentId}/maintenance`)
}

export async function logMaintenance(
  equipmentId: string,
  body: MaintenanceCreateInput,
): Promise<MaintenanceCreateResult> {
  const res = await apiFetch(`/api/v2/equipments/${equipmentId}/maintenance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
  return (await res.json()) as MaintenanceCreateResult
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export function listNotifications(householdId: string, limit = 20): Promise<AppNotification[]> {
  const q = new URLSearchParams({
    household_id: householdId,
    limit: String(limit),
    offset: '0',
  })
  return apiGetJson<AppNotification[]>(`/api/v2/notifications?${q.toString()}`)
}

export async function respondNotification(
  id: string,
  response: 'used_up' | 'extended',
  days?: number,
): Promise<AppNotification> {
  const res = await apiFetch(`/api/v2/notifications/${id}/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ response, days: days ?? 3 }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`)
  }
  return (await res.json()) as AppNotification
}
