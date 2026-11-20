/**
 * TanStack Query client — design doc §8.7.
 *
 * Mini Program không có event focus/online của browser nên tắt
 * refetchOnWindowFocus / refetchOnReconnect; refetch khi nối lại được nối
 * tay tới Taro.onNetworkStatusChange → queryClient.invalidateQueries()
 * (xem app.tsx). Mọi queryFn đều qua request<T>() (§8.4).
 */
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 30_000,
      retry: 2,
    },
  },
})

export default queryClient
