/**
 * Providers (H5) — MUI ThemeProvider + CssBaseline + QueryClient +
 * Toast/Dialog hosts (§8.3). H5 bỏ qua tabBar.custom nên phải ẩn tab bar
 * built-in của Taro, custom TabBar render thay.
 */
import { useEffect } from 'react'
import type { PropsWithChildren } from 'react'
import Taro from '@tarojs/taro'
import { CssBaseline, ThemeProvider } from '@mui/material'
import { QueryClientProvider } from '@tanstack/react-query'
import { muiTheme } from './ui/muiTheme'
import { queryClient } from './store/queryClient'
import { ToastHost } from './ui/primitives/Toast'
import { DialogHost } from './ui/primitives/Dialog'

export default function Providers({ children }: PropsWithChildren) {
  useEffect(() => {
    Taro.hideTabBar().catch(() => {})
  }, [])
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        {children}
        <ToastHost />
        <DialogHost />
      </QueryClientProvider>
    </ThemeProvider>
  )
}
