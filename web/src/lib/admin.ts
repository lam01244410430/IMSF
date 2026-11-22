/**
 * Typed admin API client — Dashboard Phase C (plan §4.5, shared
 * contract `~/workspace/dash-c/admin-api-contract.md` §2).
 *
 * All 13 endpoints live under `/api/v2/admin` and require the
 * `require_admin` dependency server-side (JWT + enabled user +
 * `IMSF_ADMIN_USER_IDS` allowlist). The frontend guard only decides
 * what to *show* — it is never the security boundary.
 *
 * Shapes are copied from the contract exactly; no fields are
 * invented. In particular:
 * - `GET /users` NEVER returns an openid (exact-openid lookup is
 *   server-side only).
 * - Recipe statuses are only `draft` / `published` / `hidden`
 *   (`pending` / `rejected` community approval is a later phase).
 * - `GET /receipt-jobs` returns receipt processing records from
 *   the receipts table (the receipts table IS the durable tracking;
 *   there is no separate job table and no `tracking` field).
 */
import { ApiError, apiFetch, apiGetJson } from './auth'
import type { Equipment, FridgeItem, Receipt, Transaction } from './api'

export type AdminCapability =
  | 'users:read'
  | 'users:write'
  | 'recipes:write'
  | 'audit:read'
  | 'system:read'

/** Fixed capability list in v1 (contract §2 #1). */
export const ADMIN_CAPABILITIES: readonly AdminCapability[] = [
  'users:read',
  'users:write',
  'recipes:write',
  'audit:read',
  'system:read',
]

export interface AdminMe {
  user_id: string
  name: string
  email: string
  login_method: 'email' | 'wechat'
  capabilities: AdminCapability[]
}

export interface AdminStats {
  counts: {
    users: number
    households: number
    receipts: number
    transactions: number
    inventory_items: number
    published_recipes: number
    draft_recipes: number
    hidden_recipes: number
  }
  exceptions: {
    failed_receipt_jobs: number
    overdue_cron: boolean
    unavailable_dependencies: string[]
  }
}

export type AdminLoginMethod = 'email' | 'wechat'
export type AdminUserStatus = 'enabled' | 'disabled'

export interface AdminUserListItem {
  id: string
  name: string
  email: string
  login_method: AdminLoginMethod
  status: AdminUserStatus
  created_at: string | null
}

export interface AdminUserHousehold {
  household_id: string
  name: string
  role: 'owner' | 'member'
}

export interface AdminUserDetail {
  id: string
  name: string
  email: string
  login_method: AdminLoginMethod
  status: AdminUserStatus
  disabled_at: string | null
  created_at: string | null
  households: AdminUserHousehold[]
  counts: {
    receipts: number
    transactions: number
    inventory_items: number
    equipments: number
  }
}

export type HouseholdRecordType =
  | 'receipts'
  | 'transactions'
  | 'inventory'
  | 'equipment'

/** The four record types reuse the existing public shapes. */
export type HouseholdRecordItem = Receipt | Transaction | FridgeItem | Equipment

export interface HouseholdRecordsResult {
  items: HouseholdRecordItem[]
  total: number
}

export type AdminHealthStatus =
  | 'healthy'
  | 'unavailable'
  | 'offline_expected'
  | 'unknown'

export interface AdminHealth {
  checked_at: string | null
  api: {
    status: AdminHealthStatus
    latency_ms: number | null
    commit: string | null
    version: string | null
  }
  postgres: { status: AdminHealthStatus; latency_ms: number | null }
  redis: { status: AdminHealthStatus; latency_ms: number | null }
  gpu: {
    status: AdminHealthStatus
    expected_off: boolean
    embedding_model: string | null
    affected: string[]
  }
  cron: {
    last_run: string | null
    last_success: string | null
    next_run: string | null
    status: string
  }
  receipt_worker: {
    status: string
    queued: number
    running: number
    failed: number
    oldest_waiting: string | null
    last_completed: string | null
    heartbeat_at: string | null
  }
  vercel: {
    web_url: string | null
    api_url: string | null
    api_note: string | null
  }
}

export type AdminJobStatus = 'running' | 'success' | 'failed'

export interface AdminJobRun {
  id: string
  job_name: string
  started_at: string
  finished_at: string | null
  status: AdminJobStatus
  notifications_created: number | null
  error: string | null
  duration_ms: number | null
}

export interface AdminJobs {
  cron: {
    last_run: string | null
    last_success: string | null
    next_run: string | null
    status: string
  }
  history: AdminJobRun[]
  worker_heartbeat: { at: string | null; status: string }
}

/**
 * One receipt processing record (contract §2 #9): a row of the
 * receipts table, newest first. `status` is one of
 * pending / processing / completed / failed / needs_review.
 */
export interface AdminReceiptJob {
  id: string
  status: string
  store_name?: string | null
  total_amount?: number
  currency?: string | null
  error_message?: string | null
  processed_at?: string | null
  created_at?: string | null
  [key: string]: unknown
}

export interface AdminReceiptJobsResult {
  items: AdminReceiptJob[]
  total: number
}

export type AdminRecipeStatus = 'draft' | 'published' | 'hidden'

export interface AdminRecipe {
  id: string
  title: string
  status: AdminRecipeStatus
  author: string | null
  source_url: string | null
  category: string | null
  language: string | null
  updated_at: string | null
}

export interface AdminRecipeDetail extends AdminRecipe {
  description: string | null
  difficulty: string | null
  taste: string | null
  slug: string | null
  cover_image: string | null
  steps_json: unknown
  cook_time: number | null
  ingredients?: unknown
}

/** POST /recipes body (contract §2 #11). `status` is always `draft`
 *  on create — the caller never sends it. */
export interface AdminRecipeCreateInput {
  title: string
  description?: string | null
  source_url?: string | null
  category?: string | null
  language?: string | null
  difficulty?: string | null
  taste?: string | null
  slug?: string | null
  author?: string | null
  cover_image?: string | null
  steps_json?: unknown
  cook_time?: number | null
  ingredients?: unknown
}

/** PATCH /recipes/{id} allowlist (contract §2 #12). Unknown fields
 *  are rejected server-side with 400. */
export type AdminRecipePatchInput = Partial<{
  title: string
  description: string | null
  source_url: string | null
  category: string | null
  language: string | null
  difficulty: string | null
  taste: string | null
  slug: string | null
  author: string | null
  cover_image: string | null
  steps_json: unknown
  cook_time: number | null
  status: AdminRecipeStatus
}>

export interface AdminAuditEvent {
  id: string
  actor_user_id: string
  action: string
  target_type: string
  target_id: string
  created_at: string
  reason: string | null
  outcome: 'success' | 'failure'
  details: Record<string, unknown> | null
}

export interface PagedResult<T> {
  items: T[]
  total: number
}

function pageParams(limit: number, offset: number): URLSearchParams {
  return new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
}

async function throwFromResponse(res: Response): Promise<never> {
  const data = (await res.json().catch(() => null)) as {
    detail?: string
  } | null
  const message =
    typeof data?.detail === 'string' && data.detail.length > 0
      ? data.detail
      : `Request failed (${res.status})`
  throw new ApiError(res.status, message)
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await throwFromResponse(res)
  return (await res.json()) as T
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await throwFromResponse(res)
  return (await res.json()) as T
}

// ---------------------------------------------------------------------------
// Guard + overview
// ---------------------------------------------------------------------------

export function getAdminMe(): Promise<AdminMe> {
  return apiGetJson<AdminMe>('/api/v2/admin/me')
}

export function getAdminStats(): Promise<AdminStats> {
  return apiGetJson<AdminStats>('/api/v2/admin/stats')
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export function listAdminUsers(opts?: {
  q?: string
  login_method?: AdminLoginMethod
  status?: AdminUserStatus
  limit?: number
  offset?: number
}): Promise<PagedResult<AdminUserListItem>> {
  const q = pageParams(opts?.limit ?? 20, opts?.offset ?? 0)
  if (opts?.q) q.set('q', opts.q)
  if (opts?.login_method) q.set('login_method', opts.login_method)
  if (opts?.status) q.set('status', opts.status)
  return apiGetJson<PagedResult<AdminUserListItem>>(
    `/api/v2/admin/users?${q.toString()}`,
  )
}

export function getAdminUser(userId: string): Promise<AdminUserDetail> {
  return apiGetJson<AdminUserDetail>(
    `/api/v2/admin/users/${encodeURIComponent(userId)}`,
  )
}

export function listHouseholdRecords(
  householdId: string,
  opts: {
    type: HouseholdRecordType
    reason: string
    limit?: number
    offset?: number
  },
): Promise<HouseholdRecordsResult> {
  const q = pageParams(opts.limit ?? 20, opts.offset ?? 0)
  q.set('type', opts.type)
  q.set('reason', opts.reason)
  return apiGetJson<HouseholdRecordsResult>(
    `/api/v2/admin/households/${encodeURIComponent(householdId)}/records?${q.toString()}`,
  )
}

export function patchAdminUserStatus(
  userId: string,
  body: { disabled: boolean; reason: string },
): Promise<AdminUserDetail> {
  return patchJson<AdminUserDetail>(
    `/api/v2/admin/users/${encodeURIComponent(userId)}/status`,
    body,
  )
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export function getAdminHealth(): Promise<AdminHealth> {
  return apiGetJson<AdminHealth>('/api/v2/admin/health')
}

export function listAdminJobs(limit = 20): Promise<AdminJobs> {
  const q = new URLSearchParams({ limit: String(limit) })
  return apiGetJson<AdminJobs>(`/api/v2/admin/jobs?${q.toString()}`)
}

export function listAdminReceiptJobs(opts?: {
  limit?: number
  offset?: number
}): Promise<AdminReceiptJobsResult> {
  const q = pageParams(opts?.limit ?? 20, opts?.offset ?? 0)
  return apiGetJson<AdminReceiptJobsResult>(
    `/api/v2/admin/receipt-jobs?${q.toString()}`,
  )
}

// ---------------------------------------------------------------------------
// Recipes
// ---------------------------------------------------------------------------

export function listAdminRecipes(opts?: {
  status?: AdminRecipeStatus
  limit?: number
  offset?: number
}): Promise<PagedResult<AdminRecipe>> {
  const q = pageParams(opts?.limit ?? 20, opts?.offset ?? 0)
  if (opts?.status) q.set('status', opts.status)
  return apiGetJson<PagedResult<AdminRecipe>>(
    `/api/v2/admin/recipes?${q.toString()}`,
  )
}

export function createAdminRecipe(
  body: AdminRecipeCreateInput,
): Promise<AdminRecipeDetail> {
  return postJson<AdminRecipeDetail>('/api/v2/admin/recipes', body)
}

export function patchAdminRecipe(
  recipeId: string,
  body: AdminRecipePatchInput,
): Promise<AdminRecipeDetail> {
  return patchJson<AdminRecipeDetail>(
    `/api/v2/admin/recipes/${encodeURIComponent(recipeId)}`,
    body,
  )
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export function listAdminAuditEvents(opts?: {
  action?: string
  target_id?: string
  from?: string
  to?: string
  limit?: number
  offset?: number
}): Promise<PagedResult<AdminAuditEvent>> {
  const q = pageParams(opts?.limit ?? 20, opts?.offset ?? 0)
  if (opts?.action) q.set('action', opts.action)
  if (opts?.target_id) q.set('target_id', opts.target_id)
  if (opts?.from) q.set('from', opts.from)
  if (opts?.to) q.set('to', opts.to)
  return apiGetJson<PagedResult<AdminAuditEvent>>(
    `/api/v2/admin/audit-events?${q.toString()}`,
  )
}
