/**
 * Picker — H5 (MUI Dialog + danh sách lựa chọn).
 */
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItemButton,
  ListItemText,
  Button,
} from '@mui/material'
import type { PickerProps } from './Picker.types'

export default function Picker(props: PickerProps) {
  const { visible, title, options, value, onConfirm, onCancel } = props
  return (
    <Dialog open={visible} onClose={() => onCancel()} fullWidth maxWidth='xs' aria-label={title}>
      {title ? <DialogTitle>{title}</DialogTitle> : null}
      <DialogContent sx={{ p: 0 }}>
        <List>
          {options.map((opt) => (
            <ListItemButton
              key={String(opt.value)}
              selected={opt.value === value}
              onClick={() => onConfirm(opt.value)}
            >
              <ListItemText primary={opt.label} />
            </ListItemButton>
          ))}
        </List>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onCancel()}>取消</Button>
      </DialogActions>
    </Dialog>
  )
}
