/**
 * Fallback chỉ để tsc resolve được './Button' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Button.weapp.tsx / Button.h5.tsx
 * khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Button.h5'
export type { ButtonProps, ButtonVariant, ButtonSize } from './Button.types'
