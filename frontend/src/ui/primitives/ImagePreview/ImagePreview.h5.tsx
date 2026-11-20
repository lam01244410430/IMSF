/**
 * ImagePreview — H5 (MUI Dialog lightbox).
 */
import { Dialog, DialogContent, IconButton, Box, Typography } from '@mui/material'
import { Close } from '@mui/icons-material'
import { tokens } from '../../tokens'
import type { ImagePreviewProps } from './ImagePreview.types'

export default function ImagePreview(props: ImagePreviewProps) {
  const { visible, images, index = 0, onClose } = props
  const src = images[index]
  return (
    <Dialog open={visible} onClose={() => onClose()} maxWidth='md' aria-label='xem ảnh'>
      <DialogContent sx={{ position: 'relative', p: 0, bgcolor: tokens.color.onSurface }}>
        <IconButton
          onClick={() => onClose()}
          aria-label='đóng'
          sx={{ position: 'absolute', top: 8, right: 8, color: tokens.color.surface, zIndex: 1 }}
        >
          <Close />
        </IconButton>
        {src ? (
          <img src={src} alt={`ảnh ${index + 1}`} style={{ display: 'block', maxWidth: '100%' }} />
        ) : null}
        <Box sx={{ position: 'absolute', bottom: 8, left: 0, right: 0, textAlign: 'center' }}>
          <Typography variant='caption' sx={{ color: tokens.color.surface }}>
            {index + 1} / {images.length}
          </Typography>
        </Box>
      </DialogContent>
    </Dialog>
  )
}
