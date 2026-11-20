/**
 * OfflineBanner — banner amber cố định khi mất mạng (§7.3):「当前无网络，
 * 内容可能不是最新」. Render ở mỗi trang dưới PageHeader.
 */
import { Text, View } from '@tarojs/components'
import { tokens } from '../../ui/tokens'
import { useUiStore } from '../../store/ui'
import Icon from '../../ui/primitives/Icon'

export default function OfflineBanner() {
  const isOnline = useUiStore((s) => s.isOnline)
  if (isOnline) return null
  return (
    <View
      style={{
        backgroundColor: tokens.color.warningContainer,
        paddingLeft: 16,
        paddingRight: 16,
        paddingTop: 8,
        paddingBottom: 8,
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <Icon name='warning' size={16} color={tokens.color.warning} />
      <Text style={{ fontSize: 13, color: tokens.color.warning }}>当前无网络，内容可能不是最新</Text>
    </View>
  )
}
