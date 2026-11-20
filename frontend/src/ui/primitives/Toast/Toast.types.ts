/**
 * Toast — API imperative dùng chung (design doc §8.2).
 * Page gọi `showToast(message, kind)`; `ToastHost` mount 1 lần ở app shell
 * (Step 4). Weapp: NutUI Toast.show qua custom event — cần ToastHost đã
 * mount (id 'imsf-toast'). H5: MUI Snackbar qua ui store (đã có sẵn).
 */
export type ToastKind = 'success' | 'error' | 'info'

export default ToastKind
