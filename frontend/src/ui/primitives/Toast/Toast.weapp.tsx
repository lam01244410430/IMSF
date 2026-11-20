/**
 * Toast — WeChat Mini Program (NutUI React 3.0.20 Toast imperative).
 * Toast.show(selector, options) bắn custom event tới Toast đã mount với
 * cùng id — ToastHost phải được mount ở app shell (Step 4).
 */
import { Toast as NutToast } from '@nutui/nutui-react-taro'
import type { ToastKind } from './Toast.types'

export function showToast(message: string, kind: ToastKind = 'info'): void {
  NutToast.show('imsf-toast', {
    content: message,
    icon: kind === 'success' ? 'success' : kind === 'error' ? 'fail' : null,
    duration: kind === 'error' ? 3 : 2,
  })
}

export function ToastHost() {
  return <NutToast id='imsf-toast' />
}

export default ToastHost
