/**
 * App entry — Providers + network listener + session-expired handler (§8.3,
 * §7.3). Lưu ý: file này là app.tsx (không còn app.ts — Taro ưu tiên .ts
 * trước .tsx khi resolve, nên hai file không được cùng tồn tại).
 */
import { useEffect } from 'react'
import type { PropsWithChildren } from 'react'
import Taro, { useLaunch } from '@tarojs/taro'
import Providers from './providers'
import { queryClient } from './store/queryClient'
import { useUiStore } from './store/ui'
import { setSessionExpiredHandler } from './services/auth'
import { goLogin } from './config/routes'
import './app.scss'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // Không bootstrap auth ở đây: token còn thì ở lại, hết thì http layer
    // báo session-expired → login (handler đăng ký dưới).
  })

  useEffect(() => {
    setSessionExpiredHandler(() => {
      void goLogin()
    })
    const onStatus = (res: { isConnected: boolean }) => {
      useUiStore.getState().setOnline(res.isConnected)
      if (res.isConnected) void queryClient.invalidateQueries()
    }
    Taro.onNetworkStatusChange(onStatus)
    Taro.getNetworkType({
      success: (res) => useUiStore.getState().setOnline(res.networkType !== 'none'),
    }).catch(() => {})
    return () => {
      setSessionExpiredHandler(null)
      Taro.offNetworkStatusChange(onStatus)
    }
  }, [])

  return <Providers>{children}</Providers>
}

export default App
