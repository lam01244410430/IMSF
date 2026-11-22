import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PublicHeader } from '../components/PublicHeader'
import { RecipeSource } from '../components/RecipeSource'
import { fill, useLanguage } from '../lib/i18n'
import {
  fetchRecipes,
  type RecipeListItem,
  type RecipeListResponse,
} from '../lib/recipes'

const PAGE_SIZE = 20

/**
 * Recipe blog list (/blog, reform plan §6.2).
 *
 * - h1 + subtitle; search by ingredient (?ingredient=<canonical
 *   name>); grid 3 cols desktop / 2 tablet / 1 mobile, gap 24px.
 * - Card (§6.2): var(--im-surface) bg, 1px hairline var(--im-border),
 *   radius 4px (theme rule wins over §6.2's 16px -- see RADIUS NOTE
 *   below), shadow elevation 1 at rest / 2 on hover (kept per plan
 *   §6.2 -- DESIGN.md "Phase 4 rulings", F-05); cover 16:10; title
 *   16px/500 max 2 lines ellipsis; meta row 14px var(--im-muted)
 *   with REAL fields
 *   only (cook_time, ingredient_count, likes_count -- NO servings,
 *   the column does not exist); bottom row author + real like count
 *   (0 when none, never a fake number).
 * - No cover -> honest var(--im-surface-2) frame + outline image icon, NO stock
 *   photo. Loading -> skeleton cards with the same geometry; error ->
 *   error panel + retry button.
 * - EMPTY (the live state, 0 recipes): honest empty state -- and NO
 *   link to a posting page (posting is deferred).
 * - No-match search: no-match message + clear-filter button.
 * - Copy is i18n (zh/vi/en, Phase 4 F-02) via useLanguage.
 *
 * RADIUS NOTE (Phase 4, DECIDED): §6.2 fixes the card radius at
 * 16px, but the imsf-swiss theme rule is 4px everywhere (DESIGN.md /
 * index.css -- old tokens.shape card 16 was explicitly NOT copied).
 * Decision: the theme rule wins -- the card is now 4px (index.css
 * .blog-card). The card shadow is KEPT per plan §6.2 (see DESIGN.md
 * "Phase 4 rulings"). No other blog layout changed.
 */

function ImageIcon() {
  return (
    <svg
      className="blog-cover-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="2" />
      <path d="M4 18l4.5-4.5 3.5 3.5L16.5 12 20 16" />
    </svg>
  )
}

function HeartIcon() {
  return (
    <svg
      className="blog-heart-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <path d="M12 20.5C7 16.5 3 13.3 3 9.3 3 6.4 5.2 4.5 7.7 4.5c1.7 0 3.3.9 4.3 2.4 1-1.5 2.6-2.4 4.3-2.4 2.5 0 4.7 1.9 4.7 4.8 0 4-4 7.2-9 11.2z" />
    </svg>
  )
}

function RecipeCard({ recipe }: { recipe: RecipeListItem }) {
  const { t } = useLanguage()
  const metaParts: string[] = []
  if (recipe.cook_time !== null && recipe.cook_time !== undefined) {
    metaParts.push(
      fill(t['blog.cookTime'], { minutes: String(recipe.cook_time) }),
    )
  }
  metaParts.push(
    fill(t['blog.ingredientCount'], {
      count: String(recipe.ingredient_count),
    }),
  )
  return (
    <article className="blog-card">
      <Link
        to={`/blog/${recipe.id}`}
        className="blog-card-link"
        aria-label={recipe.title}
      >
        {recipe.cover_image ? (
          <img
            className="blog-card-cover"
            src={recipe.cover_image}
            alt={recipe.title}
            loading="lazy"
          />
        ) : (
          <div className="blog-card-cover blog-card-cover-empty" aria-hidden="true">
            <ImageIcon />
          </div>
        )}
        <div className="blog-card-body">
          <h2 className="blog-card-title">{recipe.title}</h2>
          <p className="blog-card-meta">{metaParts.join(' · ')}</p>
          <p className="blog-card-bottom">
            {recipe.author ? (
              <span className="blog-card-author">{recipe.author.name}</span>
            ) : null}
            <span className="blog-card-likes">
              <HeartIcon />
              {recipe.likes_count}
            </span>
          </p>
        </div>
      </Link>
      <RecipeSource
        sourceUrl={recipe.source_url}
        className="blog-card-source"
      />
    </article>
  )
}

function SkeletonCard() {
  return (
    <div className="blog-card blog-skeleton" aria-hidden="true">
      <div className="blog-card-cover blog-skeleton-cover" />
      <div className="blog-card-body">
        <div className="blog-skeleton-line blog-skeleton-title" />
        <div className="blog-skeleton-line blog-skeleton-meta" />
      </div>
    </div>
  )
}

export function BlogPage() {
  const { t } = useLanguage()
  const [params, setParams] = useSearchParams()
  const ingredient = params.get('ingredient') ?? ''
  const author = params.get('author') ?? ''
  const page = Math.max(
    0,
    Number.parseInt(params.get('page') ?? '0', 10) || 0,
  )
  const [data, setData] = useState<RecipeListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    fetchRecipes({
      ingredient: ingredient || undefined,
      author: author || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    })
      .then((result) => {
        if (!cancelled) {
          setData(result)
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
  }, [ingredient, author, page, reloadKey])

  const hasFilter = ingredient !== '' || author !== ''
  const totalPages =
    data !== null ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  function goToPage(nextPage: number) {
    const next = new URLSearchParams(params)
    if (nextPage <= 0) {
      next.delete('page')
    } else {
      next.set('page', String(nextPage))
    }
    setParams(next)
  }

  function clearFilter() {
    setParams({})
  }

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = new URLSearchParams(params)
    const value = new FormData(event.currentTarget)
      .get('search')
      ?.toString()
      .trim()
    if (value) {
      next.set('ingredient', value)
    } else {
      next.delete('ingredient')
    }
    next.delete('page')
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
        <h1 className="blog-title">{t['blog.title']}</h1>
        <p className="blog-subtitle">{t['blog.subtitle']}</p>

        <form className="blog-search" onSubmit={submitSearch} role="search">
          <label className="blog-search-label" htmlFor="blog-search-input">
            {t['blog.searchLabel']}
          </label>
          <input
            key={ingredient}
            id="blog-search-input"
            name="search"
            className="blog-search-input"
            type="search"
            defaultValue={ingredient}
            placeholder={t['blog.searchPlaceholder']}
          />
          <button type="submit" className="btn btn-primary">
            {t['blog.search']}
          </button>
        </form>

        {hasFilter && !loading && data !== null && data.total > 0 ? (
          <p className="blog-active-filter">
            {ingredient
              ? fill(t['blog.filterIngredient'], { ingredient })
              : ''}
            {ingredient && author ? ' · ' : ''}
            {author ? t['blog.filterAuthor'] : ''}
            <button
              type="button"
              className="btn btn-ghost btn-sm blog-clear-filter"
              onClick={clearFilter}
            >
              {t['blog.clearFilter']}
            </button>
          </p>
        ) : null}

        {loading ? (
          <div className="blog-grid" aria-label={t['blog.loading']}>
            {Array.from({ length: 6 }).map((_, index) => (
              <SkeletonCard key={index} />
            ))}
          </div>
        ) : error ? (
          <div className="blog-error" role="alert">
            <p>{t['blog.loadError']}</p>
            <button type="button" className="btn btn-primary" onClick={retry}>
              {t['blog.retry']}
            </button>
          </div>
        ) : data !== null && data.total === 0 ? (
          hasFilter && ingredient ? (
            <div className="blog-empty">
              <p className="blog-empty-title">
                {fill(t['blog.noMatch'], { ingredient })}
              </p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={clearFilter}
              >
                {t['blog.clearFilter']}
              </button>
            </div>
          ) : hasFilter && author ? (
            <div className="blog-empty">
              <p className="blog-empty-title">{t['blog.authorEmpty']}</p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={clearFilter}
              >
                {t['blog.clearFilter']}
              </button>
            </div>
          ) : (
            <div className="blog-empty">
              <p className="blog-empty-title">{t['blog.emptyTitle']}</p>
              <p className="blog-empty-subtitle">
                {t['blog.emptySubtitle']}
              </p>
            </div>
          )
        ) : (
          <>
            <div className="blog-grid">
              {(data?.items ?? []).map((recipe) => (
                <RecipeCard key={recipe.id} recipe={recipe} />
              ))}
            </div>
            {data !== null && data.total > PAGE_SIZE ? (
              <nav className="blog-pager" aria-label={t['blog.pagerLabel']}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={page <= 0}
                  onClick={() => goToPage(page - 1)}
                >
                  {t['blog.prevPage']}
                </button>
                <span className="blog-pager-info">
                  {fill(t['blog.pagerInfo'], {
                    page: String(page + 1),
                    total: String(data.total),
                  })}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={page + 1 >= totalPages}
                  onClick={() => goToPage(page + 1)}
                >
                  {t['blog.nextPage']}
                </button>
              </nav>
            ) : null}
          </>
        )}
      </main>
    </div>
  )
}
