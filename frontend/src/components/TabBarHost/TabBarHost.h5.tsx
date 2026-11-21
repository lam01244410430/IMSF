/**
 * TabBarHost (H5) — mount AppTabBar cố định dưới màn hình (§8.3). H5 bỏ qua
 * tabBar.custom nên custom-tab-bar không được mount; mỗi trang tab render
 * <TabBarHost /> cuối cùng. FE-04 (§12.2): trên desktop (>=1024px) trả null
 * — sidebar của DesktopShell thay thế cả nav dưới lẫn FAB.
 */
import AppTabBar from '../AppTabBar/AppTabBar'
import { useIsDesktop } from '../../hooks/useIsDesktop'

export default function TabBarHost() {
  const isDesktop = useIsDesktop()
  if (isDesktop) return null
  return <AppTabBar />
}
