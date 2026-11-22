/**
 * Admin System (/admin/system) — Dashboard Phase C (plan §4.3,
 * contract §2 #7–#9).
 *
 * Dependency statuses with check timestamps + sanitized errors
 * (API, Postgres, Redis, GPU/Ollama with "expected off", cron with
 * last/next run, receipt worker, Vercel links with imsf-api marked
 * hollow/unconfigured), job history, receipt jobs, and read-only
 * config (cron schedule, API origin without credentials, admin
 * allowlist note).
 *
 * NO secret editor, NO deploy/GPU controls, NO blind retry buttons.
 * When the health endpoint itself does not answer, the page says
 * "API unreachable" with the last successful check time (kept in
 * localStorage from the previous good check) instead of pretending
 * the system is fine. Nothing is fabricated: an empty job history
 * renders as empty, and receipt jobs are receipt processing
 * records from the receipts table — not a separate job queue
 * (contract §2 #9: the receipts table IS the durable tracking).
 */
import { useEffect, useState } from 'react'
import {
  getAdminHealth,
  listAdminJobs,
  listAdminReceiptJobs,
  type AdminHealth,
  type AdminHealthStatus,
  type AdminJobs,
  type AdminReceiptJobsResult,
} from '../../lib/admin'
import { formatDateTime } from '../../lib/format'
import { fill, useLanguage, type Dict } from '../../lib/i18n'
import { StatusChip, type ChipTone } from '../../components/StatusChip'
import { AdminLoadError, AdminPager } from './common'

const LAST_CHECK_KEY = 'imsf.admin.last_health_check'
const PAGE_SIZE = 20

function healthChip(status: AdminHealthStatus): { tone: ChipTone; key: keyof Dict } {
  switch (status) {
    case 'healthy':
      return { tone: 'success', key: 'admin.sysHealthy' }
    case 'unavailable':
      return { tone: 'error', key: 'admin.sysUnavailable' }
    case 'offline_expected':
      return { tone: 'neutral', key: 'admin.sysOfflineExpected' }
    default:
      return { tone: 'warning', key: 'admin.sysUnknown' }
  }
}

function cronStatusChip(status: string): { tone: ChipTone; key: keyof Dict } {
  // Backend cron statuses (admin.py _cron_summary):
  // healthy / overdue / failed / unknown.
  switch (status) {
    case 'healthy':
      return { tone: 'success', key: 'admin.sysHealthy' }
    case 'overdue':
      return { tone: 'warning', key: 'admin.sysOverdue' }
    case 'failed':
      return { tone: 'error', key: 'admin.sysFailed' }
    default:
      return { tone: 'warning', key: 'admin.sysUnknown' }
  }
}

function receiptJobChip(status: string): { tone: ChipTone; key: keyof Dict } {
  // Backend receipt statuses (receipts.status): pending /
  // processing / completed / failed / needs_review.
  switch (status) {
    case 'pending':
      return { tone: 'neutral', key: 'admin.jobPending' }
    case 'processing':
      return { tone: 'accent', key: 'admin.jobProcessing' }
    case 'completed':
      return { tone: 'success', key: 'admin.jobCompleted' }
    case 'failed':
      return { tone: 'error', key: 'admin.jobFailed' }
    case 'needs_review':
      return { tone: 'warning', key: 'admin.jobNeedsReview' }
    default:
      return { tone: 'warning', key: 'admin.sysUnknown' }
  }
}

function readLastCheck(): string | null {
  try {
    return window.localStorage.getItem(LAST_CHECK_KEY)
  } catch {
    return null
  }
}

function writeLastCheck(iso: string): void {
  try {
    window.localStorage.setItem(LAST_CHECK_KEY, iso)
  } catch {
    // storage unavailable — the note just falls back to "not checked yet".
  }
}

export function AdminSystemPage() {
  const { t, lang } = useLanguage()
  const [health, setHealth] = useState<AdminHealth | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [lastCheck, setLastCheck] = useState<string | null>(() => readLastCheck())
  const [attempt, setAttempt] = useState(0)

  const [jobs, setJobs] = useState<AdminJobs | null>(null)
  const [jobsError, setJobsError] = useState(false)

  const [receiptJobs, setReceiptJobs] = useState<AdminReceiptJobsResult | null>(null)
  const [receiptJobsError, setReceiptJobsError] = useState(false)
  const [receiptOffset, setReceiptOffset] = useState(0)

  useEffect(() => {
    let cancelled = false
    setHealthError(false)
    getAdminHealth()
      .then((h) => {
        if (cancelled) return
        setHealth(h)
        if (h.checked_at) {
          writeLastCheck(h.checked_at)
          setLastCheck(h.checked_at)
        }
      })
      .catch(() => {
        if (!cancelled) setHealthError(true)
      })
    listAdminJobs()
      .then((j) => {
        if (!cancelled) setJobs(j)
      })
      .catch(() => {
        if (!cancelled) setJobsError(true)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  useEffect(() => {
    let cancelled = false
    setReceiptJobsError(false)
    listAdminReceiptJobs({ limit: PAGE_SIZE, offset: receiptOffset })
      .then((r) => {
        if (!cancelled) setReceiptJobs(r)
      })
      .catch(() => {
        if (!cancelled) setReceiptJobsError(true)
      })
    return () => {
      cancelled = true
    }
  }, [receiptOffset, attempt])

  if (healthError && !health) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.sysTitle']}</h1>
        <p className="page-error">
          {fill(t['admin.sysApiUnreachable'], {
            time: lastCheck
              ? formatDateTime(lastCheck, lang)
              : t['admin.sysNoCheck'],
          })}
        </p>
        <AdminLoadError onRetry={() => setAttempt((n) => n + 1)} />
      </div>
    )
  }
  if (!health) {
    return (
      <div className="page">
        <h1 className="page-title">{t['admin.sysTitle']}</h1>
        <p className="page-note">{t['admin.loading']}</p>
      </div>
    )
  }

  const depRows: {
    name: string
    status: AdminHealthStatus
    latency: number | null
    detail?: string
  }[] = [
    {
      name: 'API',
      status: health.api.status,
      latency: health.api.latency_ms,
      detail:
        health.api.commit || health.api.version
          ? `${t['admin.sysCommit']}: ${health.api.commit ?? '—'} · ${t['admin.sysVersion']}: ${health.api.version ?? '—'}`
          : undefined,
    },
    { name: 'Postgres', status: health.postgres.status, latency: health.postgres.latency_ms },
    { name: 'Redis', status: health.redis.status, latency: health.redis.latency_ms },
    {
      name: 'GPU / Ollama',
      status: health.gpu.status,
      latency: null,
      detail: health.gpu.embedding_model
        ? health.gpu.embedding_model
        : health.gpu.expected_off
          ? t['admin.sysGpuOffNote']
          : undefined,
    },
  ]

  return (
    <div className="page">
      <h1 className="page-title">{t['admin.sysTitle']}</h1>
      <p className="page-note">
        {t['admin.sysCheckedAt']}: {formatDateTime(health.checked_at, lang)}
      </p>

      <section aria-label={t['admin.sysDeps']}>
        <h2>{t['admin.sysDeps']}</h2>
        <div className="tx-table-wrap">
          <table className="tx-table">
            <thead>
              <tr>
                <th>{t['admin.sysDeps']}</th>
                <th>{t['admin.usersStatus']}</th>
                <th>{t['admin.sysLatency']}</th>
                <th>{t['admin.sysDetail']}</th>
              </tr>
            </thead>
            <tbody>
              {depRows.map((row) => {
                const chip = healthChip(row.status)
                return (
                  <tr key={row.name}>
                    <td>{row.name}</td>
                    <td>
                      <StatusChip tone={chip.tone} label={t[chip.key]} />
                    </td>
                    <td>{row.latency === null ? '—' : `${row.latency} ms`}</td>
                    <td>{row.detail ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {health.gpu.status === 'offline_expected' && (
          <p className="page-note">{t['admin.sysGpuOffNote']}</p>
        )}
        {/* Real-backend finding (test API, 2026-11-22): with the GPU
            NOT configured off, health reports gpu.status 'unavailable'
            and no note appeared at all — yet the payload names what
            is affected. Show the backend's own affected list whenever
            the GPU is unhealthy for any other reason. */}
        {health.gpu.status !== 'healthy' &&
          health.gpu.status !== 'offline_expected' &&
          (health.gpu.affected ?? []).length > 0 && (
            <p className="page-note">
              {t['admin.sysAffected']}: {health.gpu.affected.join(', ')}
            </p>
          )}
      </section>

      <section aria-label={t['admin.sysCronStatus']}>
        <h2>{t['admin.sysCronStatus']}</h2>
        <dl className="mine-list">
          <div>
            <dt>{t['admin.sysLastRun']}</dt>
            <dd>{formatDateTime(health.cron.last_run, lang)}</dd>
          </div>
          <div>
            <dt>{t['admin.sysLastSuccess']}</dt>
            <dd>{formatDateTime(health.cron.last_success, lang)}</dd>
          </div>
          <div>
            <dt>{t['admin.sysNextRun']}</dt>
            <dd>{formatDateTime(health.cron.next_run, lang)}</dd>
          </div>
          <div>
            <dt>{t['admin.usersStatus']}</dt>
            <dd>
              <StatusChip
                tone={cronStatusChip(health.cron.status).tone}
                label={t[cronStatusChip(health.cron.status).key]}
              />
            </dd>
          </div>
          <div>
            <dt>{t['admin.sysSchedule']}</dt>
            <dd>{t['admin.sysCronSchedule']}</dd>
          </div>
        </dl>
        <h3>{t['admin.sysJobs']}</h3>
        {jobsError ? (
          <p className="page-error">{t['admin.loadError']}</p>
        ) : !jobs ? (
          <p className="page-note">{t['admin.loading']}</p>
        ) : jobs.history.length === 0 ? (
          <p className="page-empty">{t['admin.sysJobsEmpty']}</p>
        ) : (
          <div className="tx-table-wrap">
            <table className="tx-table">
              <thead>
                <tr>
                  <th>{t['admin.sysJobs']}</th>
                  <th>{t['admin.sysLastRun']}</th>
                  <th>{t['admin.usersStatus']}</th>
                  <th>{t['admin.sysDuration']}</th>
                  <th>{t['admin.sysNotifications']}</th>
                  <th>{t['admin.sysError']}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.history.map((job) => (
                  <tr key={job.id}>
                    <td>{job.job_name}</td>
                    <td>{formatDateTime(job.started_at, lang)}</td>
                    <td>
                      {job.status === 'success' ? (
                        <StatusChip tone="success" label={t['admin.auditSuccess']} />
                      ) : job.status === 'failed' ? (
                        <StatusChip tone="error" label={t['admin.sysFailed']} />
                      ) : (
                        <StatusChip tone="accent" label={t['admin.sysRunning']} />
                      )}
                    </td>
                    <td>{job.duration_ms === null ? '—' : `${job.duration_ms} ms`}</td>
                    <td>{job.notifications_created ?? '—'}</td>
                    <td>{job.error ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {jobs && (
          <p className="page-note">
            {t['admin.sysHeartbeat']}: {formatDateTime(jobs.worker_heartbeat.at, lang)} ·{' '}
            {t[cronStatusChip(jobs.worker_heartbeat.status).key]}
          </p>
        )}
      </section>

      <section aria-label={t['admin.sysWorker']}>
        <h2>{t['admin.sysWorker']}</h2>
        <dl className="mine-list">
          <div>
            <dt>{t['admin.sysQueued']}</dt>
            <dd>{health.receipt_worker.queued}</dd>
          </div>
          <div>
            <dt>{t['admin.sysRunning']}</dt>
            <dd>{health.receipt_worker.running}</dd>
          </div>
          <div>
            <dt>{t['admin.sysFailed']}</dt>
            <dd>{health.receipt_worker.failed}</dd>
          </div>
          <div>
            <dt>{t['admin.sysOldestWaiting']}</dt>
            <dd>{formatDateTime(health.receipt_worker.oldest_waiting, lang)}</dd>
          </div>
          <div>
            <dt>{t['admin.sysLastCompleted']}</dt>
            <dd>{formatDateTime(health.receipt_worker.last_completed, lang)}</dd>
          </div>
          <div>
            <dt>{t['admin.sysHeartbeat']}</dt>
            <dd>{formatDateTime(health.receipt_worker.heartbeat_at, lang)}</dd>
          </div>
        </dl>
        <h3>{t['admin.sysReceiptJobs']}</h3>
        <p className="page-note">{t['admin.sysReceiptJobsNote']}</p>
        {receiptJobsError ? (
          <p className="page-error">{t['admin.loadError']}</p>
        ) : !receiptJobs ? (
          <p className="page-note">{t['admin.loading']}</p>
        ) : receiptJobs.items.length === 0 ? (
          <p className="page-empty">{t['admin.sysReceiptJobsEmpty']}</p>
        ) : (
          <>
            <div className="tx-table-wrap">
              <table className="tx-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>{t['admin.usersStatus']}</th>
                    <th>{t['admin.sysError']}</th>
                    <th>{t['admin.usersCreated']}</th>
                  </tr>
                </thead>
                <tbody>
                  {receiptJobs.items.map((job) => {
                    const chip = receiptJobChip(job.status)
                    return (
                      <tr key={job.id}>
                        <td title={job.id}>{job.id.slice(0, 8)}</td>
                        <td>
                          <StatusChip tone={chip.tone} label={t[chip.key]} />
                        </td>
                        <td>
                          {typeof job.error_message === 'string' ? job.error_message : '—'}
                        </td>
                        <td>
                          {formatDateTime(
                            typeof job.created_at === 'string' ? job.created_at : null,
                            lang,
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <AdminPager
              total={receiptJobs.total}
              offset={receiptOffset}
              limit={PAGE_SIZE}
              onPage={setReceiptOffset}
            />
          </>
        )}
      </section>

      <section aria-label="Vercel">
        <h2>Vercel</h2>
        <dl className="mine-list">
          <div>
            <dt>imsf-web</dt>
            <dd>
              {health.vercel.web_url ? (
                <a href={health.vercel.web_url} target="_blank" rel="noreferrer">
                  {health.vercel.web_url}
                </a>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>imsf-api</dt>
            <dd>
              {health.vercel.api_url ? (
                <a href={health.vercel.api_url} target="_blank" rel="noreferrer">
                  {health.vercel.api_url}
                </a>
              ) : (
                '—'
              )}
              {health.vercel.api_note ? ` · ${health.vercel.api_note}` : ''}
            </dd>
          </div>
        </dl>
      </section>

      <section aria-label={t['admin.sysConfig']}>
        <h2>{t['admin.sysConfig']}</h2>
        <dl className="mine-list">
          <div>
            <dt>{t['admin.sysSchedule']}</dt>
            <dd>{t['admin.sysCronSchedule']}</dd>
          </div>
          <div>
            <dt>{t['admin.sysApiOrigin']}</dt>
            <dd>{window.location.origin}/api/v2</dd>
          </div>
          <div>
            <dt>{t['admin.sysAdminAllowlist']}</dt>
            <dd>{t['admin.sysAdminAllowlistNote']}</dd>
          </div>
        </dl>
      </section>
    </div>
  )
}
