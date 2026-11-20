/**
 * Toast — H5 (MUI Snackbar + Alert, đọc queue từ ui store).
 * showToast ghi vào store; store tự dismiss sau 4s (lỗi: 6s).
 */
import { Snackbar, Alert } from '@mui/material'
import { useUiStore } from '../../../store/ui'
import type { ToastKind } from './Toast.types'

export function showToast(message: string, kind: ToastKind = 'info'): void {
  useUiStore.getState().showToast(message, kind)
}

export function ToastHost() {
  const toasts = useUiStore((s) => s.toasts)
  const dismissToast = useUiStore((s) => s.dismissToast)
  const first = toasts[0]
  return (
    <Snackbar
      open={Boolean(first)}
      autoHideDuration={first?.kind === 'error' ? 6000 : 4000}
      onClose={(_, reason) => {
        if (reason !== 'clickaway' && first) dismissToast(first.id)
      }}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    >
      <Alert
        severity={first?.kind === 'info' ? 'info' : first?.kind}
        variant='filled'
        onClose={first ? () => dismissToast(first.id) : undefined}
      >
        {first?.message ?? ''}
      </Alert>
    </Snackbar>
  )
}

export default ToastHost
