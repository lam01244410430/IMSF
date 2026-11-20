/**
 * Route table — nguồn chân lý duy nhất cho navigation (design doc §8.3).
 * CHỈ router thống nhất của Taro — không react-router. Page chỉ navigate
 * qua các helper này, không hardcode path.
 *
 * Một route /receipts/{id}: nội dung đổi theo `status` (processing / review /
 * completed / failed) — deep link vĩnh viễn cho mỗi receipt (F13).
 */
import Taro from '@tarojs/taro'

export const routes = {
  upload: '/pages/upload/index',
  fridge: '/pages/fridge/index',
  recipes: '/pages/recipes/index',
  mine: '/pages/mine/index',
  login: '/pages/login/index',
  receipts: '/pages/receipts/index',
  receipt: (id: string) => `/pages/receipt/index?id=${encodeURIComponent(id)}`,
} as const

export function goReceipt(id: string): Promise<unknown> {
  return Taro.navigateTo({ url: routes.receipt(id) })
}

/** Thay Processing trong stack để Back không về spinner cũ (§5.2/§5.3). */
export function redirectToReceipt(id: string): Promise<unknown> {
  return Taro.redirectTo({ url: routes.receipt(id) })
}

export function goUpload(): Promise<unknown> {
  return Taro.switchTab({ url: routes.upload })
}

export function goLogin(): Promise<unknown> {
  return Taro.redirectTo({ url: routes.login })
}

export function goBack(): Promise<unknown> {
  return Taro.navigateBack()
}
