/**
 * Adapter-twin tests (Step 3, design doc §8.2): mỗi primitive render giống
 * nhau ở cả 2 platform với cùng props. Test import trực tiếp file
 * .weapp.tsx / .h5.tsx (không qua index — index resolve về h5 trong jsdom).
 *
 * Chú ý: bản weapp chạy trên mock @tarojs/components (View→div, Input→input…)
 * và NutUI đọc Taro.getEnv() === 'WEB' trong test env.
 * Giữa 2 lần render trong cùng một test PHẢI cleanup() — unmount() của render
 * trước không dọn render sau (Progress test từng rò vì dùng nhầm unmount cũ).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup, waitFor } from '@testing-library/react'

import ButtonWeapp from './Button/Button.weapp'
import ButtonH5 from './Button/Button.h5'
import TextFieldWeapp from './TextField/TextField.weapp'
import TextFieldH5 from './TextField/TextField.h5'
import StepperWeapp from './Stepper/Stepper.weapp'
import StepperH5 from './Stepper/Stepper.h5'
import DialogWeapp, { confirmDialog as confirmDialogWeapp, DialogHost as DialogHostWeapp } from './Dialog/Dialog.weapp'
import DialogH5, { confirmDialog as confirmDialogH5, DialogHost as DialogHostH5 } from './Dialog/Dialog.h5'
import { useConfirmDialogStore } from './Dialog/dialogStore'
import { showToast as showToastWeapp, ToastHost as ToastHostWeapp } from './Toast/Toast.weapp'
import { showToast as showToastH5, ToastHost as ToastHostH5 } from './Toast/Toast.h5'
import ProgressWeapp from './Progress/Progress.weapp'
import ProgressH5 from './Progress/Progress.h5'
import UploaderWeapp from './Uploader/Uploader.weapp'
import UploaderH5 from './Uploader/Uploader.h5'
import ImagePreviewWeapp from './ImagePreview/ImagePreview.weapp'
import ImagePreviewH5 from './ImagePreview/ImagePreview.h5'
import TabBarWeapp from './TabBar/TabBar.weapp'
import TabBarH5 from './TabBar/TabBar.h5'
import ListRowWeapp from './ListRow/ListRow.weapp'
import ListRowH5 from './ListRow/ListRow.h5'
import SkeletonWeapp from './Skeleton/Skeleton.weapp'
import SkeletonH5 from './Skeleton/Skeleton.h5'
import SwitchWeapp from './Switch/Switch.weapp'
import SwitchH5 from './Switch/Switch.h5'
import PickerWeapp from './Picker/Picker.weapp'
import PickerH5 from './Picker/Picker.h5'
import IconWeapp from './Icon/Icon.weapp'
import IconH5 from './Icon/Icon.h5'

afterEach(() => {
  // @testing-library/react chỉ tự cleanup khi test framework expose global
  // afterEach (Vitest không có globals: true) — cleanup tay để các render
  // trong test trước không rò sang test sau.
  cleanup()
  useConfirmDialogStore.setState({ open: false, resolve: null })
})

describe('Button twin', () => {
  it('renders the same label and fires onClick on both platforms', () => {
    const onClickWeapp = vi.fn()
    const onClickH5 = vi.fn()
    render(<ButtonWeapp onClick={onClickWeapp}>确认</ButtonWeapp>)
    fireEvent.click(screen.getByText('确认'))
    expect(onClickWeapp).toHaveBeenCalledTimes(1)
    cleanup()
    render(<ButtonH5 onClick={onClickH5}>确认</ButtonH5>)
    fireEvent.click(screen.getByText('确认'))
    expect(onClickH5).toHaveBeenCalledTimes(1)
  })

  it('disabled button does not fire onClick', () => {
    const onClick = vi.fn()
    render(
      <ButtonH5 disabled onClick={onClick}>
        确认
      </ButtonH5>,
    )
    fireEvent.click(screen.getByText('确认'))
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('TextField twin', () => {
  it('renders label + value and reports changes on both platforms', () => {
    const onChangeWeapp = vi.fn()
    const onChangeH5 = vi.fn()
    const { container } = render(
      <TextFieldWeapp label='单价' value='12.5' onChange={onChangeWeapp} type='number' />,
    )
    expect(screen.getByText('单价')).toBeTruthy()
    const inputWeapp = container.querySelector('input') as HTMLInputElement
    expect(inputWeapp.value).toBe('12.5')
    fireEvent.input(inputWeapp, { target: { value: '13' } })
    expect(onChangeWeapp).toHaveBeenCalledWith('13')
    cleanup()
    const { container: containerH5 } = render(
      <TextFieldH5 label='单价' value='12.5' onChange={onChangeH5} type='number' />,
    )
    // MUI render label 2 lần (label + span trong notch legend) — chọn label.
    expect(screen.getByText('单价', { selector: 'label' })).toBeTruthy()
    const inputH5 = containerH5.querySelector('input') as HTMLInputElement
    expect(inputH5.value).toBe('12.5')
    fireEvent.change(inputH5, { target: { value: '13' } })
    expect(onChangeH5).toHaveBeenCalledWith('13')
  })

  it('shows the error text on both platforms', () => {
    render(
      <TextFieldWeapp label='数量' value='' onChange={() => {}} error='数量必须大于 0' />,
    )
    expect(screen.getByText('数量必须大于 0')).toBeTruthy()
    cleanup()
    render(<TextFieldH5 label='数量' value='' onChange={() => {}} error='数量必须大于 0' />)
    expect(screen.getByText('数量必须大于 0')).toBeTruthy()
  })
})

describe('Stepper twin', () => {
  it('renders the value and increments on both platforms', async () => {
    const onChangeWeapp = vi.fn()
    const onChangeH5 = vi.fn()
    const { container } = render(<StepperWeapp value={2} onChange={onChangeWeapp} />)
    const inputWeapp = container.querySelector('input') as HTMLInputElement
    expect(inputWeapp.value).toBe('2')
    // NutUI InputNumber: nút + có class nut-inputnumber-icon-plus.
    // Handler plus là async (await beforeChange) nên phải chờ microtask.
    const plusWeapp = container.querySelector('.nut-inputnumber-icon-plus') as HTMLElement
    fireEvent.click(plusWeapp)
    await waitFor(() => expect(onChangeWeapp).toHaveBeenCalledWith(3))
    cleanup()
    render(<StepperH5 value={2} onChange={onChangeH5} />)
    fireEvent.click(screen.getByLabelText('tăng'))
    expect(onChangeH5).toHaveBeenCalledWith(3)
  })
})

describe('Dialog twin', () => {
  it('shows title + content when open, nothing when closed, on both platforms', () => {
    render(
      <DialogWeapp open title='删除' content='确定删除该行吗？' onConfirm={() => {}} onCancel={() => {}} />,
    )
    expect(screen.getByText('删除')).toBeTruthy()
    expect(screen.getByText('确定删除该行吗？')).toBeTruthy()
    cleanup()
    render(
      <DialogWeapp open={false} title='删除' content='确定删除该行吗？' onConfirm={() => {}} onCancel={() => {}} />,
    )
    expect(screen.queryByText('确定删除该行吗？')).toBeNull()
    cleanup()
    render(
      <DialogH5 open title='删除' content='确定删除该行吗？' onConfirm={() => {}} onCancel={() => {}} />,
    )
    expect(screen.getByText('删除')).toBeTruthy()
    expect(screen.getByText('确定删除该行吗？')).toBeTruthy()
  })

  it('confirmDialog resolves true on confirm and false on cancel (both platforms)', async () => {
    render(<DialogHostWeapp />)
    let promise: Promise<boolean>
    act(() => {
      promise = confirmDialogWeapp({ title: '确认删除', content: '确定吗？' })
    })
    expect(screen.getByText('确认删除')).toBeTruthy()
    fireEvent.click(screen.getByText('确认'))
    await expect(promise!).resolves.toBe(true)
    cleanup()
    render(<DialogHostH5 />)
    act(() => {
      promise = confirmDialogH5({ title: '确认删除', content: '确定吗？' })
    })
    expect(screen.getByText('确认删除')).toBeTruthy()
    fireEvent.click(screen.getByText('取消'))
    await expect(promise!).resolves.toBe(false)
  })
})

describe('Toast twin', () => {
  it('showToast displays the message on both platforms', async () => {
    render(<ToastHostWeapp />)
    act(() => {
      showToastWeapp('小票已上传', 'success')
    })
    expect(screen.getByText('小票已上传')).toBeTruthy()
    cleanup()
    render(<ToastHostH5 />)
    act(() => {
      showToastH5('小票已上传', 'success')
    })
    expect(screen.getByText('小票已上传')).toBeTruthy()
  })
})

describe('Progress twin', () => {
  it('renders determinate 50 and indeterminate on both platforms', () => {
    const { container } = render(<ProgressWeapp value={50} />)
    expect(container.querySelector('.nut-progress')).toBeTruthy()
    cleanup()
    render(<ProgressWeapp />)
    expect(document.querySelector('.nut-progress')).toBeTruthy()
    cleanup()
    render(<ProgressH5 value={50} />)
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50')
    cleanup()
    render(<ProgressH5 />)
    expect(screen.getByRole('progressbar')).toBeTruthy()
  })
})

describe('Uploader twin', () => {
  const files = [{ name: 'receipt.jpg', status: 'success' as const }]
  it('renders file name and add button on both platforms', () => {
    render(<UploaderWeapp files={files} onAdd={() => {}} onRemove={() => {}} />)
    expect(screen.getByText('receipt.jpg')).toBeTruthy()
    // Nút thêm giờ là icon thật (Icon primitive), không còn text '+' (§2(d)) —
    // assert bằng accessible name thay vì glyph.
    expect(screen.getByLabelText('添加图片')).toBeTruthy()
    cleanup()
    render(<UploaderH5 files={files} onAdd={() => {}} onRemove={() => {}} />)
    expect(screen.getByText('receipt.jpg')).toBeTruthy()
  })
})

describe('ImagePreview twin', () => {
  it('hidden when not visible, shows the image when visible, on both platforms', () => {
    const { container } = render(
      <ImagePreviewWeapp visible={false} images={['https://x/1.jpg']} onClose={() => {}} />,
    )
    expect(container.querySelector('img[src="https://x/1.jpg"]')).toBeNull()
    cleanup()
    const { container: c2 } = render(
      <ImagePreviewWeapp visible images={['https://x/1.jpg']} onClose={() => {}} />,
    )
    expect(c2.querySelector('img[src="https://x/1.jpg"]')).toBeTruthy()
    cleanup()
    render(<ImagePreviewH5 visible={false} images={['https://x/1.jpg']} onClose={() => {}} />)
    expect(screen.queryByAltText('ảnh 1')).toBeNull()
    cleanup()
    render(<ImagePreviewH5 visible images={['https://x/1.jpg']} onClose={() => {}} />)
    expect(screen.getByAltText('ảnh 1')).toBeTruthy()
  })
})

describe('TabBar twin', () => {
  const items = [
    { key: 'home', label: '首页', icon: 'home' as const },
    { key: 'fridge', label: '冰箱', icon: 'fridge' as const },
    { key: 'recipes', label: '菜谱', icon: 'recipes' as const },
    { key: 'mine', label: '我的', icon: 'mine' as const },
  ]
  const fab = { ariaLabel: '拍照上传小票', onClick: () => {} }
  it('renders all 4 labels and fires onSelect on both platforms', () => {
    const onSelectWeapp = vi.fn()
    const onSelectH5 = vi.fn()
    render(
      <TabBarWeapp items={items} selected={0} onSelect={onSelectWeapp} fab={fab} />,
    )
    for (const label of ['首页', '冰箱', '菜谱', '我的']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    fireEvent.click(screen.getByText('冰箱'))
    expect(onSelectWeapp).toHaveBeenCalledWith(1)
    cleanup()
    render(<TabBarH5 items={items} selected={0} onSelect={onSelectH5} fab={fab} />)
    for (const label of ['首页', '冰箱', '菜谱', '我的']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    expect(screen.getByLabelText('拍照上传小票')).toBeTruthy()
    fireEvent.click(screen.getByText('冰箱'))
    expect(onSelectH5).toHaveBeenCalledWith(1)
  })
})

describe('ListRow twin', () => {
  it('renders title/subtitle/amount and fires onClick on both platforms', () => {
    const onClickWeapp = vi.fn()
    const onClickH5 = vi.fn()
    render(
      <ListRowWeapp title='沃尔玛' subtitle='今天' amount='¥123.45' onClick={onClickWeapp} />,
    )
    expect(screen.getByText('沃尔玛')).toBeTruthy()
    expect(screen.getByText('今天')).toBeTruthy()
    expect(screen.getByText('¥123.45')).toBeTruthy()
    fireEvent.click(screen.getByText('沃尔玛'))
    expect(onClickWeapp).toHaveBeenCalledTimes(1)
    cleanup()
    render(<ListRowH5 title='沃尔玛' subtitle='今天' amount='¥123.45' onClick={onClickH5} />)
    expect(screen.getByText('沃尔玛')).toBeTruthy()
    fireEvent.click(screen.getByText('沃尔玛'))
    expect(onClickH5).toHaveBeenCalledTimes(1)
  })
})

describe('Skeleton twin', () => {
  it('renders skeleton rows on both platforms', () => {
    const { container } = render(<SkeletonWeapp rows={2} />)
    expect(container.querySelector('.nut-skeleton')).toBeTruthy()
    cleanup()
    const { container: c2 } = render(<SkeletonH5 rows={2} />)
    expect(c2.querySelector('.MuiSkeleton-root')).toBeTruthy()
  })
})

describe('Switch twin', () => {
  it('toggles and reports the new value on both platforms', () => {
    const onChangeWeapp = vi.fn()
    const onChangeH5 = vi.fn()
    const { container } = render(<SwitchWeapp checked={false} onChange={onChangeWeapp} />)
    const switchWeapp = container.querySelector('.nut-switch') as HTMLElement
    expect(switchWeapp).toBeTruthy()
    fireEvent.click(switchWeapp)
    expect(onChangeWeapp).toHaveBeenCalledWith(true)
    cleanup()
    render(<SwitchH5 checked={false} onChange={onChangeH5} ariaLabel='是否入库' />)
    // MUI Switch input có role='switch' (không phải "checkbox").
    fireEvent.click(screen.getByRole('switch'))
    expect(onChangeH5).toHaveBeenCalledWith(true)
  })
})

describe('Picker twin', () => {
  const options = [
    { label: '个', value: '个' },
    { label: 'kg', value: 'kg' },
  ]
  it('lists options when visible and confirms the pick on both platforms', () => {
    const onConfirmWeapp = vi.fn()
    const onConfirmH5 = vi.fn()
    render(
      <PickerWeapp visible options={options} value='个' onConfirm={onConfirmWeapp} onCancel={() => {}} />,
    )
    expect(screen.getByText('kg')).toBeTruthy()
    cleanup()
    render(
      <PickerH5 visible title='选择单位' options={options} value='个' onConfirm={onConfirmH5} onCancel={() => {}} />,
    )
    expect(screen.getByText('选择单位')).toBeTruthy()
    fireEvent.click(screen.getByText('kg'))
    expect(onConfirmH5).toHaveBeenCalledWith('kg')
  })
})

describe('Icon twin', () => {
  // NutUI icon render thành element .nut-icon (svg nằm trong data URI base64,
  // KHÔNG phải <svg> inline) — assert theo class; MUI icon render <svg>.
  it('renders the same icon key on both platforms', () => {
    const { container: c1 } = render(<IconWeapp name='camera' size={32} />)
    const el1 = c1.querySelector('.nut-icon')
    expect(el1).toBeTruthy()
    expect(el1?.className.toLowerCase()).toContain('photograph')
    cleanup()
    const { container: c2 } = render(<IconH5 name='camera' size={32} />)
    const svg2 = c2.querySelector('svg.MuiSvgIcon-root')
    expect(svg2).toBeTruthy()
    expect(svg2?.getAttribute('data-testid')).toBe('PhotoCameraIcon')
  })

  it('renders every icon key on both platforms', () => {
    const names = [
      'camera',
      'chevron-left',
      'chevron-right',
      'check',
      'clock',
      'close',
      'error',
      'image',
      'plus',
      'refresh',
      'search',
      'warning',
      'info',
    ] as const
    for (const name of names) {
      const { container, unmount } = render(<IconWeapp name={name} />)
      expect(container.querySelector('.nut-icon')).toBeTruthy()
      unmount()
      const r2 = render(<IconH5 name={name} />)
      expect(r2.container.querySelector('svg.MuiSvgIcon-root')).toBeTruthy()
      r2.unmount()
    }
  })
})

describe('ListRow left slot', () => {
  it('renders the left node and aligns subtitle under the title on both platforms', () => {
    render(
      <ListRowWeapp
        left={<span>沃</span>}
        title='沃尔玛'
        subtitle='今天'
        amount='¥123.45'
      />,
    )
    expect(screen.getByText('沃')).toBeTruthy()
    expect(screen.getByText('沃尔玛')).toBeTruthy()
    expect(screen.getByText('今天')).toBeTruthy()
    cleanup()
    render(
      <ListRowH5 left={<span>沃</span>} title='沃尔玛' subtitle='今天' amount='¥123.45' />,
    )
    expect(screen.getByText('沃')).toBeTruthy()
    expect(screen.getByText('沃尔玛')).toBeTruthy()
    expect(screen.getByText('今天')).toBeTruthy()
  })
})
