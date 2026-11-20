/**
 * API base URL — design doc §8.4: không hardcode IP/host nào trong src/.
 * Đọc từ biến môi trường build-time TARO_APP_API_BASE_URL (Taro load file
 * .env* kiểu dotenv). `.env*.local` gitignored cho override dev-machine.
 *
 * Dev: TARO_APP_API_BASE_URL=http://<oregon-dev-host>:8002 (host Oregon cung
 * cấp qua env/CI secret, không bao giờ commit).
 * Production: https://<production-api-domain> (quyết định của Lam, D-F4).
 */
export const API_BASE_URL = (process.env.TARO_APP_API_BASE_URL || '').replace(/\/$/, '')

export const API_PREFIX = '/api/v2'

/** Nối base URL + prefix + path thành URL đầy đủ cho một API call. */
export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${API_PREFIX}${p}`
}

/** True khi base URL đã được cấu hình (build có env). */
export function hasApiBaseUrl(): boolean {
  return API_BASE_URL.length > 0
}
