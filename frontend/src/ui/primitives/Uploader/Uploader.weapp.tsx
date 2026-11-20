/**
 * Uploader — WeChat Mini Program: lưới preview + nút thêm (dashed).
 */
import { View, Text, Image } from '@tarojs/components'
import { tokens } from '../../tokens'
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
            <Text
              style={{
                position: 'absolute',
                top: 2,
                right: 2,
                width: 20,
                height: 20,
                textAlign: 'center',
                backgroundColor: tokens.color.surface,
                borderRadius: 10,
                color: tokens.color.error,
                fontSize: 12,
                lineHeight: '20px',
              }}
              onClick={() => onRemove(i)}
            >
              ✕
            </Text>
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
        >
          <Text style={{ fontSize: 28, color: tokens.color.primary }}>+</Text>
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
