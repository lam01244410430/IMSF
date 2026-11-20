/**
 * Dialog — H5 (MUI 9.5.0 Dialog).
 * confirmDialog / DialogHost: imperative qua dialogStore (dùng chung).
 */
import {
  Dialog as MuiDialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from '@mui/material'
import { useConfirmDialogStore } from './dialogStore'
import type { ConfirmDialogOptions, DialogProps } from './Dialog.types'

export function confirmDialog(opts: ConfirmDialogOptions): Promise<boolean> {
  return useConfirmDialogStore.getState().ask(opts)
}

export function DialogHost() {
  const { open, title, content, confirmText, cancelText, close } = useConfirmDialogStore()
  return (
    <MuiDialog open={open} onClose={() => close(false)} aria-label={title}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>{content}</DialogContent>
      <DialogActions>
        <Button onClick={() => close(false)}>{cancelText}</Button>
        <Button variant='contained' onClick={() => close(true)} autoFocus>
          {confirmText}
        </Button>
      </DialogActions>
    </MuiDialog>
  )
}

export default function Dialog(props: DialogProps) {
  const { open, title, content, confirmText = '确认', cancelText = '取消', onConfirm, onCancel } = props
  return (
    <MuiDialog open={open} onClose={() => onCancel()} aria-label={title}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>{content}</DialogContent>
      <DialogActions>
        <Button onClick={() => onCancel()}>{cancelText}</Button>
        <Button variant='contained' onClick={() => onConfirm()} autoFocus>
          {confirmText}
        </Button>
      </DialogActions>
    </MuiDialog>
  )
}
