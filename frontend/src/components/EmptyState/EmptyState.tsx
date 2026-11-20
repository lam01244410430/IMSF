/**
 * EmptyState — pattern §7.2: icon outline 64px trong vòng dashed + title +
 * body + tối đa một action. Dùng cho danh sách rỗng và placeholder GĐ1.
 */
import { Text, View } from '@tarojs/components'
import { tokens } from '../../ui/tokens'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import type { IconName } from '../../ui/primitives/Icon'

export interface EmptyStateProps {
  icon: IconName
  title: string
  body: string
  actionLabel?: string
  onAction?: () => void
}

export default function EmptyState({ icon, title, body, actionLabel, onAction }: EmptyStateProps) {
  return (
    <View
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        paddingTop: 48,
        paddingBottom: 48,
        paddingLeft: 24,
        paddingRight: 24,
      }}
    >
      <View
        style={{
          width: 96,
          height: 96,
          borderRadius: 48,
          borderWidth: 1.5,
          borderStyle: 'dashed',
          borderColor: tokens.color.outline,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon name={icon} size={48} color={tokens.color.onSurfaceVariant} />
      </View>
      <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>{title}</Text>
      <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>{body}</Text>
      {actionLabel && onAction ? (
        <View style={{ marginTop: 4 }}>
          <Button variant='primary' onClick={onAction}>
            {actionLabel}
          </Button>
        </View>
      ) : null}
    </View>
  )
}
