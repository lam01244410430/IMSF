import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { PublicHeader } from '../components/PublicHeader'
import { isLoggedIn } from '../lib/auth'
import { searchKnowledge, type KnowledgeResult } from '../lib/knowledge'
import { fill, useLanguage } from '../lib/i18n'

/**
 * Knowledge search (/knowledge, reform plan §6.3).
 *
 * Blog article ingredient names link here with
 * ?q=<canonical name>. The backend endpoint needs auth, so a
 * logged-out visitor is sent to /login with a notice (same pattern
 * as the blog's like/save redirect) instead of landing on a page
 * that can only fail.
 *
 * - Search box + results from GET /api/v2/knowledge/search.
 * - Every result shows its source citation; content is the stored
 *   document text, never rewritten.
 * - No match above the similarity threshold -> honest empty state:
 *   the knowledge base has nothing on this term, and NO shelf-life
 *   figure is shown (a shelf life is never fabricated, Phase 2 §7.2).
 * - Copy is i18n (zh/vi/en, Phase 4 F-02) via useLanguage.
 */
export function KnowledgePage() {
  const { t } = useLanguage()
  const [params, setParams] = useSearchParams()
  const q = (params.get('q') ?? '').trim()
  const [results, setResults] = useState<KnowledgeResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    // Logged-out visitors are redirected below; never fire the
    // authenticated request for them (it could only fail).
    if (!isLoggedIn() || q === '') {
      setResults(null)
      setError(false)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    searchKnowledge(q)
      .then((rows) => {
        if (!cancelled) {
          setResults(rows)
          setError(false)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [q, reloadKey])

  if (!isLoggedIn()) {
    const next = `/knowledge${q === '' ? '' : `?q=${encodeURIComponent(q)}`}`
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(next)}`}
        state={{ notice: t['knowledge.loginFirst'] }}
        replace
      />
    )
  }

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = new FormData(event.currentTarget)
      .get('search')
      ?.toString()
      .trim()
    const next = new URLSearchParams(params)
    if (value) {
      next.set('q', value)
    } else {
      next.delete('q')
    }
    setParams(next)
  }

  function retry() {
    setError(false)
    setLoading(true)
    setReloadKey((key) => key + 1)
  }

  return (
    <div>
      <PublicHeader />
      <main className="blog-page">
        <h1 className="blog-title">{t['knowledge.title']}</h1>
        <p className="blog-subtitle">{t['knowledge.subtitle']}</p>

        <form className="blog-search" onSubmit={submitSearch} role="search">
          <label className="blog-search-label" htmlFor="knowledge-search-input">
            {t['blog.searchLabel']}
          </label>
          <input
            key={q}
            id="knowledge-search-input"
            name="search"
            className="blog-search-input"
            type="search"
            defaultValue={q}
            placeholder={t['blog.searchPlaceholder']}
          />
          <button type="submit" className="btn btn-primary">
            {t['blog.search']}
          </button>
        </form>

        {q === '' ? (
          <div className="blog-empty">
            <p className="blog-empty-title">{t['knowledge.hintTitle']}</p>
            <p className="blog-empty-subtitle">
              {t['knowledge.hintText']}
            </p>
          </div>
        ) : loading ? (
          <p className="blog-empty-subtitle" role="status">
            {t['knowledge.searching']}
          </p>
        ) : error ? (
          <div className="blog-error" role="alert">
            <p>{t['knowledge.searchError']}</p>
            <button type="button" className="btn btn-primary" onClick={retry}>
              {t['blog.retry']}
            </button>
          </div>
        ) : results !== null && results.length === 0 ? (
          <div className="blog-empty">
            <p className="blog-empty-title">{t['knowledge.noMatch']}</p>
            <p className="blog-empty-subtitle">
              {fill(t['knowledge.noMatchText'], { q })}
            </p>
          </div>
        ) : (
          <ul className="knowledge-list">
            {(results ?? []).map((result) => (
              <li key={`${result.title}-${result.source}`} className="knowledge-item">
                <h2 className="knowledge-item-title">{result.title}</h2>
                <p className="knowledge-item-source">
                  {fill(t['knowledge.source'], { source: result.source })}
                </p>
                <p className="knowledge-item-content">{result.content}</p>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
