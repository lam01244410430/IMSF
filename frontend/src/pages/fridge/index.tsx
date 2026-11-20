/**
 * 冰箱 — placeholder GĐ1 (§4.1): honest, không fake dữ liệu. Nội dung trống
 * theo §7.2 (icon + title + body + một action).
 */
import { View } from '@tarojs/components'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import EmptyState from '../../components/EmptyState/EmptyState'
import TabBarHost from '../../components/TabBarHost'
import { useTabBarSelected } from '../../hooks/useTabBarSelected'
import { goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'

export default function Fridge() {
  useTabBarSelected(1)
  return (
    <View style={{ paddingBottom: tokens.size.navHeight + 16 }}>
      <PageHeader title='冰箱' />
      <OfflineBanner />
      <EmptyState
        icon='image'
        title='冰箱即将上线'
        body='第一批食材入库后，这里会显示保质期提醒。'
        actionLabel='去上传小票'
        onAction={() => void goUpload()}
      />
      <TabBarHost />
    </View>
  )
}
