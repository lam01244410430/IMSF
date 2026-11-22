import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { logout, resetAuthState } from '../lib/auth'

const DETAIL = {
  id: 'recipe-1',
  title: '番茄炒蛋',
  cover_image: null,
  cook_time: 15,
  ingredient_count: 2,
  likes_count: 3,
  created_at: '2026-11-21T10:00:00+00:00',
  author: { id: 'author-1', name: '小林' },
  source_url: 'https://m.meishichina.com/recipe/455851/',
  ingredients: [
    { name: '鸡蛋', quantity: 2, unit: '个' },
    { name: '番茄', quantity: 3, unit: '个' },
  ],
  steps: [
    { text: '鸡蛋打散。', image: null },
    { text: '下锅翻炒。', image: null },
  ],
  comment_count: 0,
  saved_count: 1,
  author_recipe_count: 2,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

describe('blog article', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
    logout()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(DETAIL))),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('ingredient names link to /knowledge?q=<canonical name>', async () => {
    renderAt('/blog/recipe-1')
    expect(await screen.findByRole('heading', { name: '番茄炒蛋' })).toBeDefined()
    const eggLink = screen.getByRole('link', { name: '鸡蛋' })
    expect(eggLink.getAttribute('href')).toBe('/knowledge?q=%E9%B8%A1%E8%9B%8B')
    const tomatoLink = screen.getByRole('link', { name: '番茄' })
    expect(tomatoLink.getAttribute('href')).toBe('/knowledge?q=%E7%95%AA%E8%8C%84')
    // Amounts are real: 鸡蛋 2 个, 番茄 3 个.
    expect(screen.getByText('2 个')).toBeDefined()
    expect(screen.getByText('3 个')).toBeDefined()
    // Q11 decided: link only, NO 在冰箱里 chip.
    expect(screen.queryByText(/在冰箱里/)).toBeNull()
  })

  it('meta row shows real counts only; author block links to /blog?author=', async () => {
    renderAt('/blog/recipe-1')
    await screen.findByRole('heading', { name: '番茄炒蛋' })
    expect(screen.getByText(/烹饪时间 15分钟/)).toBeDefined()
    expect(screen.getByText(/2种食材/)).toBeDefined()
    expect(screen.getByText(/3个赞 · 1个收藏 · 0条评论/)).toBeDefined()
    // No servings anywhere: the column does not exist.
    expect(screen.queryByText(/人份/)).toBeNull()
    expect(screen.getByText('已发布 2 个菜谱')).toBeDefined()
    const authorLink = screen.getByRole('link', { name: '查看TA的其他菜谱' })
    expect(authorLink.getAttribute('href')).toBe('/blog?author=author-1')
    // Steps are numbered in accent, no icon tiles.
    expect(screen.getByText('鸡蛋打散。')).toBeDefined()
    expect(screen.getByText('下锅翻炒。')).toBeDefined()
  })

  it('article shows the source credit line under the title with a link to the source site', async () => {
    renderAt('/blog/recipe-1')
    await screen.findByRole('heading', { name: '番茄炒蛋' })
    const sourceLink = screen.getByRole('link', { name: '美食天下' })
    expect(sourceLink.getAttribute('href')).toBe(
      'https://m.meishichina.com/recipe/455851/',
    )
    expect(sourceLink.getAttribute('target')).toBe('_blank')
    expect(sourceLink.getAttribute('rel')).toBe('noopener noreferrer')
    // The credit line sits under the title/meta, before the ingredients.
    const sourceLine = sourceLink.closest('p')
    const ingredientsHeading = screen.getByRole('heading', { name: '食材' })
    expect(
      sourceLine?.compareDocumentPosition(ingredientsHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('article with no source_url shows no credit line', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse({ ...DETAIL, source_url: null })),
      ),
    )
    renderAt('/blog/recipe-1')
    await screen.findByRole('heading', { name: '番茄炒蛋' })
    expect(screen.queryByText('来源：')).toBeNull()
    expect(screen.queryByText('美食天下')).toBeNull()
  })

  it('comment area shows the honest upcoming line, no form', async () => {
    renderAt('/blog/recipe-1')
    await screen.findByRole('heading', { name: '番茄炒蛋' })
    expect(screen.getByText('评论功能即将上线')).toBeDefined()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByText(/发表评论/)).toBeNull()
  })

  it('like/save redirect to /login when logged out', async () => {
    renderAt('/blog/recipe-1')
    await screen.findByRole('heading', { name: '番茄炒蛋' })
    fireEvent.click(screen.getByRole('button', { name: /点赞/ }))
    // Redirected to the login page (with ?next= back to the article).
    expect(await screen.findByRole('heading', { name: '登录' })).toBeDefined()
  })

  it('shopping-list button is hidden when logged out', async () => {
    renderAt('/blog/recipe-1')
    await screen.findByRole('heading', { name: '番茄炒蛋' })
    expect(screen.queryByText('用这道菜生成购物清单')).toBeNull()
  })

  it('404: honest not-found panel with a link back to the list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: 'Recipe not found' }, 404),
        ),
      ),
    )
    renderAt('/blog/does-not-exist')
    expect(await screen.findByText('未找到这道菜谱，它可能已被删除或尚未发布。')).toBeDefined()
    const back = screen.getByRole('link', { name: '返回菜谱列表' })
    expect(back.getAttribute('href')).toBe('/blog')
  })
})
