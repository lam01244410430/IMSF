/**
 * Fallback chỉ để tsc resolve được './TabBar' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên TabBar.weapp.tsx /
 * TabBar.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './TabBar.h5'
export type { TabBarProps, TabBarItem, TabBarIconKey } from './TabBar.types'
