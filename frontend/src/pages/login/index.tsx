/**
 * 登录 — WeChat login (wx.login → code → POST /api/v2/auth/wechat, §8.4).
 * H5 không có wx.login: Taro.login() thất bại → hiện「请在微信中打开小程序登录」.
 */
import { useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import { useSessionStore } from '../../store/session'
import { loginWithWechat } from '../../services/auth'
import { ApiError } from '../../services/errors'
import { goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'

export default function Login() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setError(null)
    setLoading(true)
    try {
      const { code } = await Taro.login()
      const { user, households } = await loginWithWechat(code)
      useSessionStore.getState().setSession(user, households)
      void goUpload()
    } catch (e) {
      if (e instanceof ApiError) setError(e.messageZh)
      else setError('请在微信中打开小程序登录')
    } finally {
      setLoading(false)
    }
  }

  return (
    <View
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        padding: 32,
        minHeight: '80vh',
      }}
    >
      <Icon name='camera' size={64} color={tokens.color.primary} />
      <Text style={{ fontSize: 20, fontWeight: 700, color: tokens.color.onSurface }}>微信登录</Text>
      <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>
        请使用微信登录以继续
      </Text>
      {error ? (
        <Text style={{ fontSize: 13, color: tokens.color.error, textAlign: 'center' }}>{error}</Text>
      ) : null}
      <Button variant='primary' size='large' block loading={loading} onClick={() => void handleLogin()}>
        微信登录
      </Button>
    </View>
  )
}
