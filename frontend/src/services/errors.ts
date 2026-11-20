/**
 * Error mapping — design doc §8.6: status API → thông báo zh-CN cho user.
 * Page không bao giờ hardcode text status, và không chuỗi `detail` thô nào
 * từ server hiện cho user (có thể chứa nội bộ).
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly messageZh: string

  constructor(status: number, messageZh: string, code = '') {
    super(messageZh)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.messageZh = messageZh
  }
}

const STATUS_ZH: Record<number, string> = {
  400: '图片格式或大小不符合要求，请重新选择（JPG/PNG/WebP，≤10MB）',
  401: '登录已过期，请重新登录',
  403: '您没有权限查看该家庭的内容',
  404: '该内容已不存在',
  409: '这张小票已处理过，请刷新后查看',
  422: '请检查数量、单位和价格后重试',
}

export function apiErrorToZh(status: number): string {
  if (status === 0) return '网络异常，请检查网络后重试'
  if (status >= 500) return '服务器开小差了，请稍后重试'
  return STATUS_ZH[status] ?? '服务器开小差了，请稍后重试'
}

export function toApiError(status: number, code = ''): ApiError {
  return new ApiError(status, apiErrorToZh(status), code)
}
