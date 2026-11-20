/**
 * 菜谱 — placeholder GĐ1 (§4.1), song song với trang 冰箱.
 * CHÚ Ý: doc §9 chỉ cho copy của 冰箱；copy dưới là cấu trúc song song
 * ("第一批食材入库后，这里会显示菜谱推荐。") — không phải chuỗi doc chỉ định,
 * ghi vào báo cáo cuối.
 */
import { View } from '@tarojs/components'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import EmptyState from '../../components/EmptyState/EmptyState'
import TabBarHost from '../../components/TabBarHost'
import { useTabBarSelected } from '../../hooks/useTabBarSelected'
import { goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'

export default function Recipes() {
  useTabBarSelected(2)
  return (
    <View style={{ paddingBottom: tokens.size.navHeight + 16 }}>
      <PageHeader title='菜谱' />
      <OfflineBanner />
      <EmptyState
        icon='image'
        title='菜谱即将上线'
        body='第一批食材入库后，这里会显示菜谱推荐。'
        actionLabel='去上传小票'
        onAction={() => void goUpload()}
      />
      <TabBarHost />
    </View>
  )
}
