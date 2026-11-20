/**
 * Fallback chỉ để tsc resolve được './Progress' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Progress.weapp.tsx /
 * Progress.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Progress.h5'
export type { ProgressProps } from './Progress.types'
