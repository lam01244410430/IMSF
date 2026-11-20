/**
 * Fallback chỉ để tsc resolve được './Skeleton' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Skeleton.weapp.tsx /
 * Skeleton.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Skeleton.h5'
export type { SkeletonProps } from './Skeleton.types'
