/**
 * PageHeader — header tự render (§4.2): 56px, nền trắng, hairline dưới,
 * title 20px semibold + subtitle 14px, nút back chevron 44px (trang chi tiết).
 */
import { Text, View } from '@tarojs/components'
import { tokens } from '../../ui/tokens'
import Icon from '../../ui/primitives/Icon'

export interface PageHeaderProps {
  title: string
  subtitle?: string
  showBack?: boolean
  onBack?: () => void
}

export default function PageHeader({ title, subtitle, showBack, onBack }: PageHeaderProps) {
  return (
    <View
      style={{
        height: 56,
        backgroundColor: tokens.color.surface,
        borderBottomWidth: 1,
        borderBottomStyle: 'solid',
        borderBottomColor: tokens.color.divider,
        paddingLeft: 16,
        paddingRight: 16,
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
      }}
    >
      {showBack ? (
        <View
          style={{ width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: -10 }}
          onClick={() => onBack?.()}
          aria-label='返回'
        >
          <Icon name='chevron-left' size={24} color={tokens.color.onSurface} />
        </View>
      ) : null}
      <View style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Text style={{ fontSize: 20, fontWeight: 700, color: tokens.color.onSurface, lineHeight: '24px' }}>{title}</Text>
        {subtitle ? (
          <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, lineHeight: '18px' }}>{subtitle}</Text>
        ) : null}
      </View>
    </View>
  )
}
