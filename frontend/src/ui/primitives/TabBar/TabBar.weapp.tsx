/**
 * TabBar — WeChat Mini Program (NutUI React 3.0.20 Tabbar + FAB tự làm).
 * LỆCH NHỎ so với doc §4.1: @nutui/icons-react-taro 3.0.2 KHÔNG có icon
 * tủ lạnh / sách / mũ đầu bếp — dùng Store (冰箱) và List (菜谱) gần nhất;
 * label chữ vẫn đúng spec, icon chỉ là phụ trợ.
 */
import { View } from '@tarojs/components'
import { Tabbar } from '@nutui/nutui-react-taro'
import { Home, Store, List, User, Photograph } from '@nutui/icons-react-taro'
import { tokens } from '../../tokens'
import type { TabBarIconKey, TabBarProps } from './TabBar.types'

function Icon({ iconKey }: { iconKey: TabBarIconKey }) {
  const size = { width: 22, height: 22 }
  switch (iconKey) {
    case 'home':
      return <Home {...size} />
    case 'fridge':
      return <Store {...size} />
    case 'recipes':
      return <List {...size} />
    case 'mine':
      return <User {...size} />
  }
}

export default function TabBar(props: TabBarProps) {
  const { items, selected, onSelect, fab } = props
  return (
    <View
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: tokens.zIndex.bottomNavigation,
        backgroundColor: tokens.color.surface,
      }}
    >
      {/* Divider NẰM TRÊN nav, là sibling — KHÔNG bao giờ nằm trong hàng nav (§4.1, lỗi Figma đã biết). */}
      <View style={{ height: 1, backgroundColor: tokens.color.divider }} />
      <Tabbar
        value={selected}
        onSwitch={(v: number) => onSelect(v)}
        fixed={false}
        safeArea
        activeColor={tokens.color.accent}
        inactiveColor={tokens.color.onSurfaceVariant}
      >
        {items.map((item) => (
          <Tabbar.Item
            key={item.key}
            title={item.label}
            icon={<Icon iconKey={item.icon} />}
            dot={item.dot}
          />
        ))}
      </Tabbar>
      <View
        style={{
          position: 'fixed',
          left: '50%',
          bottom: tokens.size.navHeight / 2,
          transform: 'translateX(-50%)',
          width: tokens.size.fab,
          height: tokens.size.fab,
          borderRadius: tokens.shape.fab,
          backgroundColor: tokens.color.accent,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: tokens.elevation.fab,
          zIndex: tokens.zIndex.fab,
        }}
        onClick={() => fab.onClick()}
      >
        <Photograph width={26} height={26} color={tokens.color.onAccent} />
      </View>
    </View>
  )
}
