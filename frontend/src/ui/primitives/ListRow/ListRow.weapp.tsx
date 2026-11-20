/**
 * ListRow — WeChat Mini Program (NutUI React 3.0.20 Cell).
 */
import { View, Text } from '@tarojs/components'
import { Cell } from '@nutui/nutui-react-taro'
import { tokens } from '../../tokens'
import type { ListRowProps } from './ListRow.types'

export default function ListRow(props: ListRowProps) {
  const { glyph, title, subtitle, amount, chip, onClick } = props
  const titleNode = glyph ? (
    <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Text>{glyph}</Text>
      <Text>{title}</Text>
    </View>
  ) : (
    title
  )
  return (
    <Cell
      title={titleNode}
      description={subtitle}
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
