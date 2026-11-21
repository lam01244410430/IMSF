/**
 * ListRow — H5 (MUI ListItemButton).
 */
import { ListItemButton, ListItemText, Box, Typography } from '@mui/material'
import { tokens } from '../../tokens'
import type { ListRowProps } from './ListRow.types'

export default function ListRow(props: ListRowProps) {
  const { left, title, subtitle, amount, chip, onClick } = props
  return (
    <ListItemButton onClick={() => onClick?.()} sx={{ minHeight: tokens.size.receiptRowHeight }}>
      {left}
      <ListItemText primary={title} secondary={subtitle} />
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.5 }}>
        {amount ? <Typography variant='subtitle1'>{amount}</Typography> : null}
        {chip}
      </Box>
    </ListItemButton>
  )
}
