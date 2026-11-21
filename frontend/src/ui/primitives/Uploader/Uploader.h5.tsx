/**
 * Uploader — H5 (MUI): lưới preview + nút thêm (dashed).
 */
import { Box, IconButton } from '@mui/material'
import { Delete, Add } from '@mui/icons-material'
import { tokens } from '../../tokens'
import Progress from '../Progress'
import type { UploaderProps } from './Uploader.types'

export default function Uploader(props: UploaderProps) {
  const { files, onAdd, onRemove, disabled, progress } = props
  return (
    <Box>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {files.map((f, i) => (
          <Box
            key={`${f.name}-${i}`}
            sx={{
              position: 'relative',
              width: 80,
              height: 80,
              borderRadius: `${tokens.shape.base}px`,
              overflow: 'hidden',
              bgcolor: tokens.color.surfaceVariant,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {f.src ? (
              <img src={f.src} alt={f.name} style={{ width: 80, height: 80, objectFit: 'cover' }} />
            ) : (
              <Box sx={{ fontSize: 12, color: tokens.color.onSurfaceVariant, px: 1 }}>
                {f.name}
              </Box>
            )}
            <IconButton
              size='small'
              onClick={() => onRemove(i)}
              aria-label={`xóa ${f.name}`}
              sx={{ position: 'absolute', top: 2, right: 2, bgcolor: tokens.color.surface }}
            >
              <Delete fontSize='small' />
            </IconButton>
          </Box>
        ))}
        <Box
          sx={{
            width: 80,
            height: 80,
            borderRadius: `${tokens.shape.base}px`,
            border: `1.5px dashed ${tokens.color.outline}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: disabled ? 'default' : 'pointer',
            opacity: disabled ? 0.5 : 1,
          }}
          onClick={() => {
            if (!disabled) onAdd()
          }}
          role='button'
          aria-label='thêm ảnh'
        >
          <Add sx={{ color: tokens.color.accent, fontSize: 28 }} />
        </Box>
      </Box>
      {progress !== undefined ? (
        <Box sx={{ mt: 1 }}>
          <Progress value={progress} />
        </Box>
      ) : null}
    </Box>
  )
}
