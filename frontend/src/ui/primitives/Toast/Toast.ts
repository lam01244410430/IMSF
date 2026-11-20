/**
 * Fallback chỉ để tsc resolve được './Toast' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Toast.weapp.tsx /
 * Toast.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default, showToast, ToastHost } from './Toast.h5'
export type { ToastKind } from './Toast.types'
