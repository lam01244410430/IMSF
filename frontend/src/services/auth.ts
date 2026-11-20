/**
 * Auth — design doc §8.4.
 *
 * - Storage: `Taro.setStorageSync / getStorageSync / removeStorageSync`,
 *   key `imsf2.*` (H5 map sang localStorage, weapp sang Mini Program storage).
 * - Access token 15 phút / refresh token 7 ngày (backend mint).
 *   Refresh response chỉ trả access token mới — refresh token cũ giữ nguyên.
 * - Single-flight: `refreshPromise` in-memory; mọi request gặp 401 trong lúc
 *   refresh đang chạy await cùng promise.
 * - Refresh chủ động: khi access token còn < 60s tới hạn (decode `exp` từ
 *   JWT payload phía client — chỉ kiểm tra hạn, không verify).
 * - WeChat login: `Taro.login()` → code → POST /api/v2/auth/wechat.
 *   H5 không có wx.login — màn login hiện "请在微信中打开小程序登录" (GĐ1
 *   Mini-Program-first; auth H5 SMS OTP là GĐ2 D4, không lén đưa vào đây).
 *
 * File này KHÔNG import http.ts (tránh circular import): refresh/login dùng
 * Taro.request trực tiếp.
 */
import Taro from '@tarojs/taro'
import { apiUrl } from '../config/env'
import { ApiError, apiErrorToZh } from './errors'

export const STORAGE_KEYS = {
  access: 'imsf2.access_token',
  refresh: 'imsf2.refresh_token',
  household: 'imsf2.household_id',
} as const

export interface AuthUser {
  id: string
  wechat_openid?: string
}

export interface HouseholdSummary {
  id: string
  name: string
}

const REFRESH_EARLY_MS = 60_000

let refreshPromise: Promise<string> | null = null
let sessionExpiredHandler: (() => void) | null = null
let sessionExpiredNotified = false

export function setSessionExpiredHandler(fn: (() => void) | null): void {
  sessionExpiredHandler = fn
  sessionExpiredNotified = false
}

export function notifySessionExpired(): void {
  if (sessionExpiredHandler && !sessionExpiredNotified) {
    sessionExpiredNotified = true
    sessionExpiredHandler()
  }
}

function storageGet(key: string): string {
  try {
    return (Taro.getStorageSync(key) as string) || ''
  } catch {
    return ''
  }
}

function storageSet(key: string, value: string): void {
  try {
    Taro.setStorageSync(key, value)
  } catch {
    // storage đầy / không khả dụng — token chỉ giữ in-memory qua lần gọi sau
  }
}

function storageRemove(key: string): void {
  try {
    Taro.removeStorageSync(key)
  } catch {
    // bỏ qua
  }
}

export function getAccessToken(): string {
  return storageGet(STORAGE_KEYS.access)
}

export function getRefreshToken(): string {
  return storageGet(STORAGE_KEYS.refresh)
}

export function getStoredHouseholdId(): string | null {
  return storageGet(STORAGE_KEYS.household) || null
}

export function setStoredHouseholdId(id: string): void {
  storageSet(STORAGE_KEYS.household, id)
}

export function setTokens(accessToken: string, refreshToken: string): void {
  storageSet(STORAGE_KEYS.access, accessToken)
  storageSet(STORAGE_KEYS.refresh, refreshToken)
}

export function setAccessToken(accessToken: string): void {
  storageSet(STORAGE_KEYS.access, accessToken)
}

/** Xóa cả hai token (refresh fail → màn login, §8.4). */
export function clearTokens(): void {
  storageRemove(STORAGE_KEYS.access)
  storageRemove(STORAGE_KEYS.refresh)
}

export function logout(): void {
  clearTokens()
  storageRemove(STORAGE_KEYS.household)
}

export function isLoggedIn(): boolean {
  return getAccessToken().length > 0
}

function base64UrlDecode(input: string): string {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  if (typeof globalThis.atob === 'function') return globalThis.atob(padded)
  // Fallback thủ công khi không có atob (một số runtime Mini Program).
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  let out = ''
  let acc = 0
  let bits = 0
  for (const ch of padded) {
    if (ch === '=') break
    acc = (acc << 6) | chars.indexOf(ch)
    bits += 6
    if (bits >= 8) {
      bits -= 8
      out += String.fromCharCode((acc >> bits) & 0xff)
    }
  }
  return decodeURIComponent(
    out
      .split('')
      .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
      .join(''),
  )
}

/** Decode `exp` từ JWT payload — chỉ kiểm tra hạn, không verify. */
export function decodeJwtExp(token: string): number | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const json = JSON.parse(base64UrlDecode(payload)) as { exp?: number }
    return typeof json.exp === 'number' ? json.exp * 1000 : null
  } catch {
    return null
  }
}

export function accessTokenExpiresInMs(): number | null {
  const token = getAccessToken()
  if (!token) return null
  const exp = decodeJwtExp(token)
  if (exp === null) return null
  return exp - Date.now()
}

/** Refresh khi access token còn < 60s tới hạn — gọi trước khi bắt đầu upload. */
export async function ensureFreshAccessToken(): Promise<void> {
  const remaining = accessTokenExpiresInMs()
  if (remaining !== null && remaining < REFRESH_EARLY_MS) {
    await refreshAccessToken()
  }
}

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const rt = getRefreshToken()
    if (!rt) throw new ApiError(401, apiErrorToZh(401))
    let res: Taro.request.SuccessCallbackResult
    try {
      res = await Taro.request({
        url: apiUrl('/auth/refresh'),
        method: 'POST',
        data: { refresh_token: rt },
        header: { 'Content-Type': 'application/json' },
        timeout: 15_000,
      })
    } catch {
      throw new ApiError(0, apiErrorToZh(0))
    }
    if (res.statusCode !== 200) {
      throw new ApiError(res.statusCode, apiErrorToZh(res.statusCode))
    }
    const access = (res.data as { access_token?: string } | null)?.access_token
    if (!access) throw new ApiError(401, apiErrorToZh(401))
    setAccessToken(access)
    return access
  })()
  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

export async function loginWithWechat(code: string): Promise<{
  user: AuthUser
  households: HouseholdSummary[]
}> {
  let res: Taro.request.SuccessCallbackResult
  try {
    res = await Taro.request({
      url: apiUrl('/auth/wechat'),
      method: 'POST',
      data: { code },
      header: { 'Content-Type': 'application/json' },
      timeout: 15_000,
    })
  } catch {
    throw new ApiError(0, apiErrorToZh(0))
  }
  if (res.statusCode !== 200) {
    throw new ApiError(res.statusCode, apiErrorToZh(res.statusCode))
  }
  const data = res.data as {
    access_token?: string
    refresh_token?: string
    user?: AuthUser
    households?: HouseholdSummary[]
  }
  if (!data.access_token || !data.refresh_token || !data.user) {
    throw new ApiError(401, apiErrorToZh(401))
  }
  setTokens(data.access_token, data.refresh_token)
  return { user: data.user, households: data.households ?? [] }
}
