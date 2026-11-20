/**
 * Fallback chỉ để tsc resolve được './Switch' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Switch.weapp.tsx /
 * Switch.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Switch.h5'
export type { SwitchProps } from './Switch.types'
