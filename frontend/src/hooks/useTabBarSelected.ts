/**
 * useTabBarSelected — đồng bộ tab đang chọn vào ui store + custom tab bar
 * (weapp) khi trang tab hiện (§8.3). H5 không có getTabBar — bỏ qua lặng.
 */
import { getCurrentInstance, useDidShow } from '@tarojs/taro'
import { useUiStore } from '../store/ui'

export function useTabBarSelected(index: number): void {
  useDidShow(() => {
    useUiStore.getState().setTabBarSelected(index)
    try {
      const page = getCurrentInstance().page as
        | { getTabBar?: () => { setData?: (data: Record<string, unknown>) => void } }
        | undefined
      page?.getTabBar?.()?.setData?.({ selected: index })
    } catch {
      // H5 / trang không có tab bar — bỏ qua.
    }
  })
}
