/**
 * ImagePreview — props dùng chung (design doc §8.2).
 * Dùng xem lại ảnh tiểu phiếu ở Screen 03 (§5.3, max-height 240px do page
 * quy định, primitive chỉ hiển thị lightbox).
 */
export interface ImagePreviewProps {
  visible: boolean
  images: string[]
  index?: number
  onClose: () => void
}

export default ImagePreviewProps
