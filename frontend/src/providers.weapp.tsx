/**
 * Providers (weapp) — NutUI ConfigProvider (locale zh-CN) + QueryClient +
 * Toast/Dialog hosts (§8.3). Không dùng process.env.TARO_ENV ở đây: chính
 * file .weapp.tsx là nhánh platform.
 */
import type { PropsWithChildren } from 'react'
import { ConfigProvider } from '@nutui/nutui-react-taro'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './store/queryClient'
import { nutuiLocale } from './ui/nutuiTheme'
import { ToastHost } from './ui/primitives/Toast'
import { DialogHost } from './ui/primitives/Dialog'

export default function Providers({ children }: PropsWithChildren) {
  return (
    <ConfigProvider locale={nutuiLocale}>
      <QueryClientProvider client={queryClient}>
        {children}
        <ToastHost />
        <DialogHost />
      </QueryClientProvider>
    </ConfigProvider>
  )
}
