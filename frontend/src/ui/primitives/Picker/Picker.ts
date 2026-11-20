/**
 * Fallback chỉ để tsc resolve được './Picker' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Picker.weapp.tsx /
 * Picker.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Picker.h5'
export type { PickerProps, PickerOption } from './Picker.types'
