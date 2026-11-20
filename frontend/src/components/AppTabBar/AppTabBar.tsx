/**
 * AppTabBar — thanh tab chuẩn của app (§4.1, §8.3): 4 tab + FAB chụp ảnh.
 * Một component duy nhất, mount ở hai nơi: custom-tab-bar (weapp) và
 * TabBarHost (H5). FAB ở tab khác → mở camera khi về upload (ui store).
 */
import Taro from '@tarojs/taro'
import TabBar from '../../ui/primitives/TabBar'
import { useUiStore } from '../../store/ui'
import { routes } from '../../config/routes'

const TAB_PATHS = [routes.upload, routes.fridge, routes.recipes, routes.mine]

export default function AppTabBar() {
  const selected = useUiStore((s) => s.tabBarSelected)
  const onSelect = (index: number) => {
    // Primitive chỉ có 4 item (FAB là nút riêng) — index ánh xạ thẳng TAB_PATHS.
    const path = TAB_PATHS[index]
    if (path) void Taro.switchTab({ url: path })
  }
  return (
    <TabBar
      items={[
        { key: 'upload', label: '首页', icon: 'home' },
        { key: 'fridge', label: '冰箱', icon: 'fridge' },
        { key: 'recipes', label: '菜谱', icon: 'recipes' },
        { key: 'mine', label: '我的', icon: 'mine' },
      ]}
      selected={selected}
      onSelect={onSelect}
      fab={{
        ariaLabel: '拍照上传小票',
        onClick: () => {
          useUiStore.getState().setOpenCameraOnShow(true)
          void Taro.switchTab({ url: routes.upload })
        },
      }}
    />
  )
}
