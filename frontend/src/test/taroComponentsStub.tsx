/**
 * Stub module cho alias '@tarojs/components' trong vitest.config.ts.
 * Mỗi component là một DOM element giữ nguyên children/className — cùng
 * định nghĩa với mock trong setup.ts (setup giữ vi.mock để test file import
 * trực tiếp cũng được mock; alias đảm bảo import từ node_modules cũng vậy).
 */
import React from 'react'

const stub = (tag: string) =>
  React.forwardRef<unknown, Record<string, unknown>>(function Stub(props, ref) {
    const { children, ...rest } = props
    return React.createElement(tag, { ...rest, ref }, children as React.ReactNode)
  })

export const View = stub('div')
export const Text = stub('span')
export const Image = stub('img')
export const Button = stub('button')
export const Input = stub('input')
export const ScrollView = stub('div')
export const Swiper = stub('div')
export const SwiperItem = stub('div')
export const Form = stub('form')
export const Label = stub('label')
export const Navigator = stub('a')
export const Icon = stub('i')
export const Progress = stub('div')
export const Switch = stub('input')
export const Picker = stub('div')
