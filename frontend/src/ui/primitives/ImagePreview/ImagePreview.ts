/**
 * Fallback chỉ để tsc resolve được './ImagePreview' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên ImagePreview.weapp.tsx /
 * ImagePreview.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './ImagePreview.h5'
export type { ImagePreviewProps } from './ImagePreview.types'
