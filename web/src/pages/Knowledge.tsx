import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { PublicHeader } from '../components/PublicHeader'
import { isLoggedIn } from '../lib/auth'
import { searchKnowledge, type KnowledgeResult } from '../lib/knowledge'

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
 * - Copy is hardcoded zh, like the blog pages it links from.
 */
export function KnowledgePage() {
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
        state={{ notice: '请先登录后查看知识库。' }}
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
        <h1 className="blog-title">知识查询</h1>
        <p className="blog-subtitle">查食材的保质期和保存方法，来自知识库原文</p>

        <form className="blog-search" onSubmit={submitSearch} role="search">
          <label className="blog-search-label" htmlFor="knowledge-search-input">
            按食材搜索
          </label>
          <input
            key={q}
            id="knowledge-search-input"
            name="search"
            className="blog-search-input"
            type="search"
            defaultValue={q}
            placeholder="按食材搜索，比如：鸡蛋"
          />
          <button type="submit" className="btn btn-primary">
            搜索
          </button>
        </form>

        {q === '' ? (
          <div className="blog-empty">
            <p className="blog-empty-title">输入食材名称开始查询</p>
            <p className="blog-empty-subtitle">
              比如「鸡蛋」「牛奶」；结果来自知识库原文，并注明来源。
            </p>
          </div>
        ) : loading ? (
          <p className="blog-empty-subtitle" role="status">
            查询中…
          </p>
        ) : error ? (
          <div className="blog-error" role="alert">
            <p>查询失败，请检查网络后重试。</p>
            <button type="button" className="btn btn-primary" onClick={retry}>
              重试
            </button>
          </div>
        ) : results !== null && results.length === 0 ? (
          <div className="blog-empty">
            <p className="blog-empty-title">未找到相关知识</p>
            <p className="blog-empty-subtitle">
              知识库中暂无与「{q}」相关的内容，未返回任何保质期信息。
            </p>
          </div>
        ) : (
          <ul className="knowledge-list">
            {(results ?? []).map((result) => (
              <li key={`${result.title}-${result.source}`} className="knowledge-item">
                <h2 className="knowledge-item-title">{result.title}</h2>
                <p className="knowledge-item-source">来源：{result.source}</p>
                <p className="knowledge-item-content">{result.content}</p>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
