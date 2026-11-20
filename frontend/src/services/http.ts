/**
 * Request wrapper — design doc §8.4.
 * Transport: `Taro.request` — KHÔNG axios, KHÔNG raw fetch (không XHR/fetch
 * trên weapp). Một wrapper phục vụ cả hai target, zero branch platform ở
 * call site.
 *
 * - Throw `ApiError` (xem errors.ts); non-2xx không bao giờ resolve.
 * - Timeout: 15s JSON (60s upload — xem upload.ts).
 * - Retry: chỉ lỗi mạng/timeout (không nhận HTTP status) và 502/503/504;
 *   tối đa 2 retry cho GET, backoff 500ms → 1.5s; không bao giờ retry 4xx;
 *   không bao giờ auto-retry POST không idempotent (confirm).
 * - 401: refresh single-flight (auth.ts), retry mỗi request đã queue một lần.
 */
import Taro from '@tarojs/taro'
import { apiUrl } from '../config/env'
import { ApiError, apiErrorToZh } from './errors'
import { clearTokens, getAccessToken, notifySessionExpired, refreshAccessToken } from './auth'

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  body?: unknown
  /** Mặc định true — gắn Authorization: Bearer <access>. */
  auth?: boolean
  /** Mặc định 15_000 (call JSON). */
  timeoutMs?: number
  /** Mặc định: 2 cho GET khi lỗi mạng, 0 cho POST. */
  retries?: number
  idempotencyKey?: string
}

export const DEFAULT_TIMEOUT_MS = 15_000
const RETRY_BACKOFF_MS = [500, 1500]

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function isRetryable(err: unknown): boolean {
  return (
    err instanceof ApiError && (err.status === 0 || err.status === 502 || err.status === 503 || err.status === 504)
  )
}

async function doRequest<T>(path: string, opts: RequestOptions): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (opts.auth !== false) {
    const token = getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey
  let res: Taro.request.SuccessCallbackResult
  try {
    res = await Taro.request({
      url: apiUrl(path),
      method: (opts.method ?? 'GET') as Taro.request.Option['method'],
      data: opts.body as Record<string, unknown>,
      header: headers,
      timeout: opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    })
  } catch {
    throw new ApiError(0, apiErrorToZh(0))
  }
  const status = res.statusCode
  if (status >= 200 && status < 300) return res.data as T
  throw new ApiError(status, apiErrorToZh(status))
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? 'GET'
  const maxRetries = opts.retries ?? (method === 'GET' ? 2 : 0)
  let attempt = 0
  let refreshed = false
  for (;;) {
    try {
      return await doRequest<T>(path, opts)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && opts.auth !== false && !refreshed) {
        refreshed = true
        try {
          await refreshAccessToken()
        } catch {
          clearTokens()
          notifySessionExpired()
          throw err
        }
        continue // retry một lần với token mới
      }
      if (isRetryable(err) && attempt < maxRetries) {
        await sleep(RETRY_BACKOFF_MS[Math.min(attempt, RETRY_BACKOFF_MS.length - 1)])
        attempt += 1
        continue
      }
      throw err
    }
  }
}
