/**
 * Taro mock — tách riêng module để vi.mock factory trong setup.ts có thể
 * import nó (factory hoisted không được tham chiếu biến top-level của file
 * setup; import từ file khác là cách làm theo docs Vitest).
 *
 * Storage là Map in-memory (get/set/removeStorageSync).
 */
import { vi } from 'vitest'

const storage = new Map<string, unknown>()

export const taroMock = {
  request: vi.fn(),
  uploadFile: vi.fn(),
  downloadFile: vi.fn(),
  chooseImage: vi.fn(),
  compressImage: vi.fn(),
  getFileInfo: vi.fn(),
  login: vi.fn(),
  getStorageSync: vi.fn((key: string) => storage.get(key) ?? ''),
  setStorageSync: vi.fn((key: string, value: unknown) => {
    storage.set(key, value)
  }),
  removeStorageSync: vi.fn((key: string) => {
    storage.delete(key)
  }),
  getNetworkType: vi.fn(),
  onNetworkStatusChange: vi.fn(),
  navigateTo: vi.fn(),
  redirectTo: vi.fn(),
  switchTab: vi.fn(),
  navigateBack: vi.fn(),
  reLaunch: vi.fn(),
  showToast: vi.fn(),
  hideTabBar: vi.fn(),
  previewImage: vi.fn(),
  getSystemInfoSync: vi.fn(() => ({ windowWidth: 375, windowHeight: 812, safeArea: { top: 44, bottom: 778 } })),
  getCurrentInstance: vi.fn(() => ({ router: { params: {} } })),
  useLoad: vi.fn(),
  useDidShow: vi.fn(),
  useRouter: vi.fn(() => ({ params: {} })),
  eventCenter: { on: vi.fn(), off: vi.fn(), trigger: vi.fn() },
}

export function __resetTaroStorage(): void {
  storage.clear()
}
