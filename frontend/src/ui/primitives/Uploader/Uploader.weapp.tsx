/**
 * Uploader — WeChat Mini Program: lưới preview + nút thêm (dashed).
 */
import { View, Text, Image } from '@tarojs/components'
import { tokens } from '../../tokens'
import Icon from '../Icon'
import Progress from '../Progress'
import type { UploaderProps } from './Uploader.types'

export default function Uploader(props: UploaderProps) {
  const { files, onAdd, onRemove, disabled, progress } = props
  return (
    <View>
      <View style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {files.map((f, i) => (
          <View
            key={`${f.name}-${i}`}
            style={{
              position: 'relative',
              width: 80,
              height: 80,
              borderRadius: tokens.shape.base,
              overflow: 'hidden',
              backgroundColor: tokens.color.surfaceVariant,
            }}
          >
            {f.src ? (
              <Image src={f.src} mode='aspectFill' style={{ width: 80, height: 80 }} />
            ) : (
              <Text style={{ fontSize: 12, color: tokens.color.onSurfaceVariant }}>{f.name}</Text>
            )}
            <View
              style={{
                position: 'absolute',
                top: 2,
                right: 2,
                width: 20,
                height: 20,
                backgroundColor: tokens.color.surface,
                borderRadius: 10,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              role='button'
              aria-label={`移除 ${f.name}`}
              onClick={() => onRemove(i)}
            >
              <Icon name='close' size={12} color={tokens.color.error} />
            </View>
          </View>
        ))}
        <View
          style={{
            width: 80,
            height: 80,
            borderRadius: tokens.shape.base,
            border: `1.5px dashed ${tokens.color.outline}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: disabled ? 0.5 : 1,
          }}
          onClick={() => {
            if (!disabled) onAdd()
          }}
          role='button'
          aria-label='添加图片'
        >
          <Icon name='plus' size={28} color={tokens.color.accent} />
        </View>
      </View>
      {progress !== undefined ? (
        <View style={{ marginTop: 8 }}>
          <Progress value={progress} />
        </View>
      ) : null}
    </View>
  )
}
