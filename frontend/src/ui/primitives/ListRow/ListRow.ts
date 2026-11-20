/**
 * Fallback chỉ để tsc resolve được './ListRow' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên ListRow.weapp.tsx /
 * ListRow.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './ListRow.h5'
export type { ListRowProps } from './ListRow.types'
