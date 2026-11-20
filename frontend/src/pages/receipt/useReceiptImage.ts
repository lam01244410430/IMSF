/**
 * useReceiptImage — ảnh gốc của tiểu phiếu (§5.2/§5.3), cache theo id để
 * Processing và Review dùng chung một lần tải (staleTime Infinity — ảnh
 * không đổi sau upload).
 */
import { useQuery } from '@tanstack/react-query'
import { fetchReceiptImageSrc } from '../../services/receipts'

export function useReceiptImage(receiptId: string | null) {
  return useQuery({
    queryKey: ['receipt-image', receiptId],
    queryFn: () => fetchReceiptImageSrc(receiptId as string),
    enabled: Boolean(receiptId),
    staleTime: Infinity,
  })
}
