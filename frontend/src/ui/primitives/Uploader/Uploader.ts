/**
 * Fallback chỉ để tsc resolve được './Uploader' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Uploader.weapp.tsx /
 * Uploader.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Uploader.h5'
export type { UploaderProps, UploaderFileItem } from './Uploader.types'
