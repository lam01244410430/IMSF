/**
 * Dialog — WeChat Mini Program (NutUI React 3.0.20 Dialog, khai báo).
 * confirmDialog / DialogHost: imperative qua dialogStore (dùng chung).
 */
import { Dialog as NutDialog } from '@nutui/nutui-react-taro'
import { useConfirmDialogStore } from './dialogStore'
import type { ConfirmDialogOptions, DialogProps } from './Dialog.types'

export function confirmDialog(opts: ConfirmDialogOptions): Promise<boolean> {
  return useConfirmDialogStore.getState().ask(opts)
}

export function DialogHost() {
  const { open, title, content, confirmText, cancelText, close } = useConfirmDialogStore()
  return (
    <NutDialog
      visible={open}
      title={title}
      content={content}
      confirmText={confirmText}
      cancelText={cancelText}
      onConfirm={() => close(true)}
      onCancel={() => close(false)}
    />
  )
}

export default function Dialog(props: DialogProps) {
  const { open, title, content, confirmText = '确认', cancelText = '取消', onConfirm, onCancel } = props
  return (
    <NutDialog
      visible={open}
      title={title}
      content={content}
      confirmText={confirmText}
      cancelText={cancelText}
      onConfirm={() => onConfirm()}
      onCancel={() => onCancel()}
    />
  )
}
