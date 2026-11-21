/**
 * ListRow — WeChat Mini Program (NutUI React 3.0.20 Cell).
 */
import { View, Text } from '@tarojs/components'
import { Cell } from '@nutui/nutui-react-taro'
import { tokens } from '../../tokens'
import type { ListRowProps } from './ListRow.types'

export default function ListRow(props: ListRowProps) {
  const { left, title, subtitle, amount, chip, onClick } = props
  // Khi có `left`, subtitle render trong cột title (căn dưới title, không
  // nằm dưới vòng tròn) — đúng layout §5.1. Khi không có, giữ Cell mặc định.
  const titleNode = left ? (
    <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 12 }}>
      {left}
      <View style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Text
          style={{
            fontSize: tokens.typography.subtitle1.size,
            fontWeight: tokens.typography.subtitle1.weight,
            color: tokens.color.onSurface,
          }}
        >
          {title}
        </Text>
        {subtitle ? (
          <Text style={{ fontSize: tokens.typography.body2.size, color: tokens.color.onSurfaceVariant }}>
            {subtitle}
          </Text>
        ) : null}
      </View>
    </View>
  ) : (
    title
  )
  return (
    <Cell
      title={titleNode}
      description={left ? undefined : subtitle}
      clickable={Boolean(onClick)}
      onClick={() => onClick?.()}
      extra={
        <View
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 4,
          }}
        >
          {amount ? (
            <Text
              style={{
                fontSize: tokens.typography.subtitle1.size,
                fontWeight: tokens.typography.subtitle1.weight,
                color: tokens.color.onSurface,
              }}
            >
              {amount}
            </Text>
          ) : null}
          {chip}
        </View>
      }
    />
  )
}
