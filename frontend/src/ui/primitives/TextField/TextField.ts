/**
 * Fallback chỉ để tsc resolve được './TextField' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên TextField.weapp.tsx /
 * TextField.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './TextField.h5'
export type { TextFieldProps, TextFieldType, TextFieldInputMode } from './TextField.types'
