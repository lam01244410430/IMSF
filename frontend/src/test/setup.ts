/**
 * Vitest setup — mock @tarojs/taro + @tarojs/components để test service và
 * component chạy trong jsdom mà không cần runtime Mini Program.
 *
 * Mock object sống trong ./taroMock (import từ file khác — factory của
 * vi.mock không được tham chiếu biến top-level của file này).
 * process.env.TARO_ENV mặc định 'h5' trong test.
 */
import { vi } from 'vitest'
import React from 'react'
import { taroMock } from './taroMock'

process.env.TARO_ENV = 'h5'

vi.mock('@tarojs/taro', () => ({
  default: taroMock,
  ...taroMock,
}))

// @tarojs/components → stub DOM element giữ nguyên children/className.
const stub = (tag: string) =>
  React.forwardRef<unknown, Record<string, unknown>>(function Stub(props, ref) {
    const { children, ...rest } = props
    return React.createElement(tag, { ...rest, ref }, children as React.ReactNode)
  })

vi.mock('@tarojs/components', () => ({
  View: stub('div'),
  Text: stub('span'),
  Image: stub('img'),
  Button: stub('button'),
  Input: stub('input'),
  ScrollView: stub('div'),
  Swiper: stub('div'),
  SwiperItem: stub('div'),
  Form: stub('form'),
  Label: stub('label'),
  Navigator: stub('a'),
  Icon: stub('i'),
  Progress: stub('div'),
  Switch: stub('input'),
  Picker: stub('div'),
}))
