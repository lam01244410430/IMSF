/**
 * Taro mock — tách riêng module để vi.mock factory trong setup.ts có thể
 * import nó (factory hoisted không được tham chiếu biến top-level của file
 * setup; import từ file khác là cách làm theo docs Vitest).
 *
 * Storage là Map in-memory (get/set/removeStorageSync).
 * eventCenter là pub/sub thật (không phải stub rỗng) vì NutUI Toast.show /
 * Dialog dùng nó để kích hoạt component đã mount.
 *
 * Mỗi API export riêng lẻ (named export) để taroStub.ts có thể
 * `export *` sang alias '@tarojs/taro' trong vitest.config.ts.
 */
import { vi } from 'vitest'

const storage = new Map<string, unknown>()

type Listener = (...args: unknown[]) => void
const listeners = new Map<string, Set<Listener>>()

export const eventCenter = {
  on: vi.fn((event: string, cb: Listener) => {
    if (!listeners.has(event)) listeners.set(event, new Set())
    listeners.get(event)!.add(cb)
  }),
  off: vi.fn((event: string, cb?: Listener) => {
    if (!cb) listeners.delete(event)
    else listeners.get(event)?.delete(cb)
  }),
  trigger: vi.fn((event: string, ...args: unknown[]) => {
    listeners.get(event)?.forEach((cb) => cb(...args))
  }),
}

export const request = vi.fn()
export const uploadFile = vi.fn()
export const downloadFile = vi.fn()
export const chooseImage = vi.fn()
export const compressImage = vi.fn()
export const getFileInfo = vi.fn()
export const login = vi.fn()
export const getStorageSync = vi.fn((key: string) => storage.get(key) ?? '')
export const setStorageSync = vi.fn((key: string, value: unknown) => {
  storage.set(key, value)
})
export const removeStorageSync = vi.fn((key: string) => {
  storage.delete(key)
})
export const getNetworkType = vi.fn()
export const onNetworkStatusChange = vi.fn()
export const navigateTo = vi.fn()
export const redirectTo = vi.fn()
export const switchTab = vi.fn()
export const navigateBack = vi.fn()
export const reLaunch = vi.fn()
export const showToast = vi.fn()
export const hideTabBar = vi.fn()
export const previewImage = vi.fn()
export const getSystemInfoSync = vi.fn(() => ({
  windowWidth: 375,
  windowHeight: 812,
  safeArea: { top: 44, bottom: 778 },
}))
export const getEnv = vi.fn(() => 'WEB')
export const getCurrentInstance = vi.fn(() => ({ router: { params: {} } }))
export const useLoad = vi.fn()
export const useDidShow = vi.fn()
export const usePullDownRefresh = vi.fn()
export const stopPullDownRefresh = vi.fn()
export const pageScrollTo = vi.fn()
export const offNetworkStatusChange = vi.fn()
export const useRouter = vi.fn(() => ({ params: {} }))

export const taroMock = {
  request,
  uploadFile,
  downloadFile,
  chooseImage,
  compressImage,
  getFileInfo,
  login,
  getStorageSync,
  setStorageSync,
  removeStorageSync,
  getNetworkType,
  onNetworkStatusChange,
  navigateTo,
  redirectTo,
  switchTab,
  navigateBack,
  reLaunch,
  showToast,
  hideTabBar,
  previewImage,
  getSystemInfoSync,
  getEnv,
  getCurrentInstance,
  useLoad,
  useDidShow,
  usePullDownRefresh,
  stopPullDownRefresh,
  pageScrollTo,
  offNetworkStatusChange,
  useRouter,
  eventCenter,
}

export function __resetTaroStorage(): void {
  storage.clear()
}
