/**
 * 我的 — household switcher + hiển thị chỉ đọc (§8.3): tên nhà, vai trò,
 * tiền tệ / múi giờ / ngôn ngữ mặc định, đăng xuất. Không có số thành viên
 * (API GET /households không trả member count).
 */
import { Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import TabBarHost from '../../components/TabBarHost'
import Button from '../../ui/primitives/Button'
import ListRow from '../../ui/primitives/ListRow'
import { useTabBarSelected } from '../../hooks/useTabBarSelected'
import { useSessionStore } from '../../store/session'
import { listHouseholds } from '../../services/households'
import { logout } from '../../services/auth'
import { goLogin, goSpending, goTransactions } from '../../config/routes'
import { tokens } from '../../ui/tokens'

export default function Mine() {
  useTabBarSelected(3)
  const session = useSessionStore()
  const householdsQuery = useQuery({
    queryKey: ['households'],
    queryFn: () => listHouseholds(),
    enabled: session.isLoggedIn,
  })
  const households = householdsQuery.data ?? []
  const current = households.find((h) => h.id === session.currentHouseholdId)

  const handleLogout = () => {
    logout()
    session.clearSession()
    void goLogin()
  }

  return (
    <View style={{ paddingBottom: tokens.size.navHeight + 16 }}>
      <PageHeader title='我的' />
      <OfflineBanner />
      <View style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {!session.isLoggedIn ? (
          <View
            style={{
              backgroundColor: tokens.color.surface,
              borderRadius: tokens.shape.base,
              padding: 16,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: 8,
            }}
          >
            <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>请先登录</Text>
            <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>登录后即可使用全部功能</Text>
            <Button variant='primary' onClick={() => void goLogin()}>
              去登录
            </Button>
          </View>
        ) : (
          <>
            <View style={{ backgroundColor: tokens.color.surface, borderRadius: tokens.shape.base }}>
              <ListRow title='家庭账本' subtitle={current?.name ?? session.households[0]?.name ?? '—'} />
              <ListRow title='我的角色' subtitle={current?.role ?? '—'} />
              <ListRow title='默认货币' subtitle={current?.default_currency ?? 'CNY'} />
              <ListRow title='时区' subtitle={current?.timezone ?? 'Asia/Shanghai'} />
              <ListRow title='语言' subtitle={current?.locale ?? 'zh-CN'} />
            </View>
            {/* FE-03: sổ chi tiêu thủ công — entry 记账 trong section 家庭账本 (§6 hàng 4). */}
            <View style={{ backgroundColor: tokens.color.surface, borderRadius: tokens.shape.base }}>
              <ListRow title='记账' subtitle='手动记录每一笔支出' onClick={() => void goTransactions()} />
              <ListRow title='消费统计' subtitle='每月支出汇总' onClick={() => void goSpending()} />
            </View>
            {households.length > 1 ? (
              <View>
                <Text style={{ fontSize: 14, fontWeight: 600, color: tokens.color.onSurface }}>切换家庭账本</Text>
                <View
                  style={{
                    backgroundColor: tokens.color.surface,
                    borderRadius: tokens.shape.base,
                    marginTop: 8,
                  }}
                >
                  {households.map((h) => (
                    <ListRow
                      key={h.id}
                      title={h.name}
                      subtitle={h.id === session.currentHouseholdId ? '当前账本' : undefined}
                      onClick={() => session.setCurrentHousehold(h.id)}
                    />
                  ))}
                </View>
              </View>
            ) : null}
            <Button variant='outline' onClick={handleLogout}>
              退出登录
            </Button>
          </>
        )}
      </View>
      <TabBarHost />
    </View>
  )
}
