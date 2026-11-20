/**
 * TabBar — props dùng chung (design doc §8.2, §4.1).
 * Icon truyền bằng key (không truyền ReactNode) để mỗi platform dùng icon
 * set native của mình. FAB 56px, nhô lên 16px, z-index > nav (§3.3).
 */
export type TabBarIconKey = 'home' | 'fridge' | 'recipes' | 'mine'

export interface TabBarItem {
  key: string
  label: string
  icon: TabBarIconKey
  dot?: boolean
}

export interface TabBarProps {
  items: TabBarItem[]
  selected: number
  onSelect: (index: number) => void
  fab: {
    ariaLabel: string
    onClick: () => void
  }
}

export default TabBarProps
