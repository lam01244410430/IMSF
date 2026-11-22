/**
 * Admin System tests — dependency statuses, cron, receipt worker,
 * Vercel links, read-only config (contract §2 #7–#9).
 */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminSystemPage } from './System'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const HEALTH = {
  checked_at: '2026-11-22T01:00:00Z',
  api: { status: 'healthy', latency_ms: 12, commit: 'a833acd', version: '0.1.0' },
  postgres: { status: 'healthy', latency_ms: 3 },
  redis: { status: 'healthy', latency_ms: 2 },
  gpu: {
    status: 'offline_expected',
    expected_off: true,
    embedding_model: 'bge-m3',
    affected: ['knowledge search'],
  },
  cron: {
    last_run: '2026-11-22T00:00:00Z',
    last_success: '2026-11-22T00:00:00Z',
    next_run: '2026-11-23T00:00:00Z',
    status: 'ok',
  },
  receipt_worker: {
    status: 'unknown',
    queued: 0,
    running: 0,
    failed: 1,
    oldest_waiting: null,
    last_completed: '2026-11-21T10:00:00Z',
    heartbeat_at: null,
  },
  vercel: {
    web_url: 'https://imsf-web.vercel.app',
    api_url: 'https://imsf-api.vercel.app',
    api_note: 'hollow/unconfigured',
  },
}

const JOBS = {
  cron: {
    last_run: '2026-11-22T00:00:00Z',
    last_success: '2026-11-22T00:00:00Z',
    next_run: '2026-11-23T00:00:00Z',
    status: 'ok',
  },
  history: [
    {
      id: 'job-1',
      job_name: 'daily',
      started_at: '2026-11-22T00:00:00Z',
      finished_at: '2026-11-22T00:00:05Z',
      status: 'success',
      notifications_created: 2,
      error: null,
      duration_ms: 5123,
    },
  ],
  worker_heartbeat: { at: null, status: 'unknown' },
}

const RECEIPT_JOBS = {
  items: [
    {
      id: 'job-abc123',
      status: 'failed',
      error: 'OCR timeout',
      created_at: '2026-11-21T09:00:00Z',
    },
  ],
  total: 1,
}

describe('AdminSystemPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function stubFetch(overrides: { health?: unknown; healthStatus?: number; jobs?: unknown; receiptJobs?: unknown } = {}) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/admin/health'))
          return Promise.resolve(
            jsonResponse(overrides.health ?? HEALTH, overrides.healthStatus ?? 200),
          )
        if (url.startsWith('/api/v2/admin/jobs'))
          return Promise.resolve(jsonResponse(overrides.jobs ?? JOBS))
        if (url.startsWith('/api/v2/admin/receipt-jobs'))
          return Promise.resolve(jsonResponse(overrides.receiptJobs ?? RECEIPT_JOBS))
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  }

  function renderPage() {
    return render(
      <MemoryRouter>
        <AdminSystemPage />
      </MemoryRouter>,
    )
  }

  it('shows dependency statuses with the GPU expected-off label', async () => {
    stubFetch()
    renderPage()
    // Section heading + table header share the label.
    expect((await screen.findAllByText('依赖状态')).length).toBe(2)
    expect(screen.getByText('已关闭（预期）')).toBeDefined()
    expect(screen.getByText('知识搜索不可用；GPU 已按配置关闭。')).toBeDefined()
    expect(screen.getByText('bge-m3')).toBeDefined()
    expect(screen.getByText(/a833acd/)).toBeDefined()
  })

  it('GPU unavailable (not expected off) → shows the affected features, not the off note', async () => {
    stubFetch({
      health: {
        ...HEALTH,
        gpu: {
          status: 'unavailable',
          expected_off: false,
          embedding_model: 'bge-m3',
          affected: ['knowledge search'],
        },
      },
    })
    renderPage()
    expect(await screen.findByText('不可用')).toBeDefined()
    expect(screen.getByText('受影响: knowledge search')).toBeDefined()
    expect(screen.queryByText('知识搜索不可用；GPU 已按配置关闭。')).toBeNull()
  })

  it('shows cron runs, job history and the receipt worker counts', async () => {
    stubFetch()
    renderPage()
    // Job-history heading + jobs table header share the label.
    expect((await screen.findAllByText('任务历史')).length).toBe(2)
    expect(screen.getByText('daily')).toBeDefined()
    expect(screen.getByText('5123 ms')).toBeDefined()
    expect(screen.getByText('OCR timeout')).toBeDefined()
    // Cron schedule shows in the cron block and in read-only config.
    expect(screen.getAllByText('每天 08:00（Asia/Shanghai）').length).toBe(2)
  })

  it('shows Vercel links with the imsf-api hollow note', async () => {
    stubFetch()
    renderPage()
    expect(await screen.findByText('https://imsf-web.vercel.app')).toBeDefined()
    expect(screen.getByText(/hollow\/unconfigured/)).toBeDefined()
  })

  it('receipt-job tracking unavailable → honest note, no fake jobs', async () => {
    stubFetch({ receiptJobs: { items: [], total: 0, tracking: 'unavailable' } })
    renderPage()
    expect(await screen.findByText('小票任务跟踪暂不可用')).toBeDefined()
    expect(screen.queryByText('OCR timeout')).toBeNull()
  })

  it('empty job history → honest empty state, never fabricated runs', async () => {
    stubFetch({ jobs: { ...JOBS, history: [] } })
    renderPage()
    expect(await screen.findByText('暂无任务记录')).toBeDefined()
  })

  it('health endpoint down → "API unreachable" with last check, not a green board', async () => {
    window.localStorage.setItem(
      'imsf.admin.last_health_check',
      '2026-11-21T01:00:00Z',
    )
    stubFetch({ healthStatus: 500, health: null })
    renderPage()
    expect(await screen.findByText(/API 不可达/)).toBeDefined()
    expect(screen.getByRole('button', { name: '重试' })).toBeDefined()
  })
})
