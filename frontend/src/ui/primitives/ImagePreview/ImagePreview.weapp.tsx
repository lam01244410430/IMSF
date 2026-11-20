/**
 * ImagePreview — WeChat Mini Program (NutUI React 3.0.20 ImagePreview).
 */
import { ImagePreview as NutImagePreview } from '@nutui/nutui-react-taro'
import type { ImagePreviewProps } from './ImagePreview.types'

export default function ImagePreview(props: ImagePreviewProps) {
  const { visible, images, index = 0, onClose } = props
  return (
    <NutImagePreview
      visible={visible}
      images={images.map((src) => ({ src }))}
      value={index}
      onClose={() => onClose()}
    />
  )
}
