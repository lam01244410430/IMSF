/**
 * Fallback chỉ để tsc resolve được './Dialog' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Dialog.weapp.tsx /
 * Dialog.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default, confirmDialog, DialogHost } from './Dialog.h5'
export type { DialogProps, ConfirmDialogOptions } from './Dialog.types'
