/**
 * TabBarHost (H5) — mount AppTabBar cố định dưới màn hình (§8.3). H5 bỏ qua
 * tabBar.custom nên custom-tab-bar không được mount; mỗi trang tab render
 * <TabBarHost /> cuối cùng.
 */
import AppTabBar from '../AppTabBar/AppTabBar'

export default function TabBarHost() {
  return <AppTabBar />
}
