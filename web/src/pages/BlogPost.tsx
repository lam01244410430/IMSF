import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PublicHeader } from '../components/PublicHeader'
import { RecipeSource } from '../components/RecipeSource'
import { ApiError, isLoggedIn } from '../lib/auth'
import { fill, useLanguage } from '../lib/i18n'
import {
  createShoppingListFromRecipe,
  fetchRecipe,
  formatDate,
  formatQuantity,
  likeRecipe,
  saveRecipe,
  unlikeRecipe,
  unsaveRecipe,
  type RecipeDetail,
} from '../lib/recipes'

/**
 * Recipe article (/blog/:id, reform plan §6.3).
 *
 * - Cover full-width 16:9 (max content 1200px), alt = the real title.
 * - h1 + meta row: author · date · cook time · ingredient count ·
 *   likes / saves / comments -- ALL real numbers, never fabricated.
 *   No servings anywhere (no such column exists).
 * - Ingredients, one line each: canonical name + quantity + unit
 *   (e.g. 鸡蛋 2 个); each name LINKS to /knowledge?q=<canonical
 *   name>. NO 在冰箱里 chip (plan §10 Q11 decided: link only).
 * - Steps: numbered list 1, 2, 3... (numbers in accent
 *   var(--im-accent-text)
 *   18px/700, no icon tiles), one short paragraph per step + step
 *   image only if the author provided one (never a fake illustration).
 * - Author block: name + real count of their recipes + link
 *   /blog?author=<id>.
 * - 点赞 / 收藏 with real counts. NOT logged in -> clicking goes to
 *   /login with a clear message (navigation state `notice`, which the
 *   Wave 2 login form renders) -- never silently does nothing.
 * - Comment count shown (real); the comment area shows the
 *   comments-coming-soon note (comments DEFERRED -- no comment form).
 * - Copy is i18n (zh/vi/en, Phase 4 F-02) via useLanguage.
 * - Bottom button 用这道菜生成购物清单 (POST
 *   /api/v2/shopping-lists/from-recipe) -- shown ONLY when logged in.
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

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      className="blog-action-icon"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <path d="M12 20.5C7 16.5 3 13.3 3 9.3 3 6.4 5.2 4.5 7.7 4.5c1.7 0 3.3.9 4.3 2.4 1-1.5 2.6-2.4 4.3-2.4 2.5 0 4.7 1.9 4.7 4.8 0 4-4 7.2-9 11.2z" />
    </svg>
  )
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      className="blog-action-icon"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <path d="M6 3h12v18l-6-4.5L6 21V3z" />
    </svg>
  )
}

export function BlogPostPage() {
  const { t } = useLanguage()
  const { id } = useParams()
  const navigate = useNavigate()
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [liked, setLiked] = useState(false)
  const [saved, setSaved] = useState(false)
  const [likesCount, setLikesCount] = useState(0)
  const [actionError, setActionError] = useState<string | null>(null)
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [listBusy, setListBusy] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    fetchRecipe(id)
      .then((result) => {
        if (cancelled) return
        setRecipe(result)
        setLiked(result.liked ?? false)
        setSaved(result.saved ?? false)
        setLikesCount(result.likes_count)
        setError(false)
        setNotFound(false)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true)
        } else {
          setError(true)
        }
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, reloadKey])

  function retry() {
    setError(false)
    setNotFound(false)
    setLoading(true)
    setReloadKey((key) => key + 1)
  }

  function requireLogin(action: string) {
    navigate(`/login?next=${encodeURIComponent(`/blog/${id ?? ''}`)}`, {
      state: { notice: fill(t['blogpost.loginFirst'], { action }) },
    })
  }

  async function toggleLike() {
    if (!recipe || !id) return
    if (!isLoggedIn()) {
      requireLogin(t['blogpost.loginLikeAction'])
      return
    }
    setActionError(null)
    try {
      const result = liked
        ? await unlikeRecipe(id)
        : await likeRecipe(id)
      setLiked(result.liked)
      setLikesCount(result.likes_count)
    } catch {
      setActionError(t['blogpost.actionFailed'])
    }
  }

  async function toggleSave() {
    if (!recipe || !id) return
    if (!isLoggedIn()) {
      requireLogin(t['blogpost.loginSaveAction'])
      return
    }
    setActionError(null)
    try {
      const result = saved ? await unsaveRecipe(id) : await saveRecipe(id)
      setSaved(result.saved)
    } catch {
      setActionError(t['blogpost.actionFailed'])
    }
  }

  async function generateShoppingList() {
    if (!recipe || !id) return
    setListBusy(true)
    setListMessage(null)
    try {
      await createShoppingListFromRecipe(id)
      setListMessage(t['blogpost.listCreated'])
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setListMessage(t['blogpost.listExists'])
      } else {
        setListMessage(t['blogpost.listFailed'])
      }
    } finally {
      setListBusy(false)
    }
  }

  const metaParts: string[] = []
  if (recipe) {
    if (recipe.author) metaParts.push(recipe.author.name)
    const date = formatDate(recipe.created_at)
    if (date) metaParts.push(date)
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
    metaParts.push(
      fill(t['blogpost.counts'], {
        likes: String(likesCount),
        saved: String(recipe.saved_count),
        comments: String(recipe.comment_count),
      }),
    )
  }

  return (
    <div>
      <PublicHeader />
      <main className="blog-article">
        {!id || notFound ? (
          <div className="blog-error" role="alert">
            <p>{t['blogpost.notFound']}</p>
            <Link to="/blog" className="btn btn-primary">
              {t['blogpost.backToList']}
            </Link>
          </div>
        ) : loading ? (
          <div className="blog-article-skeleton" aria-label={t['blog.loading']}>
            <div className="blog-skeleton-cover" />
            <div className="blog-skeleton-line blog-skeleton-title" />
            <div className="blog-skeleton-line blog-skeleton-meta" />
          </div>
        ) : error || recipe === null ? (
          <div className="blog-error" role="alert">
            <p>{t['blog.loadError']}</p>
            <button type="button" className="btn btn-primary" onClick={retry}>
              {t['blog.retry']}
            </button>
          </div>
        ) : (
          <>
            {recipe.cover_image ? (
              <img
                className="blog-article-cover"
                src={recipe.cover_image}
                alt={recipe.title}
              />
            ) : (
              <div
                className="blog-article-cover blog-card-cover-empty"
                aria-hidden="true"
              >
                <ImageIcon />
              </div>
            )}
            <h1 className="blog-title">{recipe.title}</h1>
            <div className="blog-article-head">
              <p className="blog-article-meta">{metaParts.join(' · ')}</p>
              <RecipeSource sourceUrl={recipe.source_url} />
            </div>

            <section aria-labelledby="blog-ingredients-heading">
              <h2 id="blog-ingredients-heading" className="blog-section-title">
                {t['blogpost.ingredients']}
              </h2>
              <ul className="blog-ingredients">
                {recipe.ingredients.map((ingredient, index) => (
                  <li key={index} className="blog-ingredient">
                    <Link
                      to={`/knowledge?q=${encodeURIComponent(ingredient.name)}`}
                    >
                      {ingredient.name}
                    </Link>
                    <span className="blog-ingredient-amount">
                      {[
                        ingredient.quantity !== null
                          ? formatQuantity(ingredient.quantity)
                          : null,
                        ingredient.unit,
                      ]
                        .filter((part) => part !== null && part !== '')
                        .join(' ')}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section aria-labelledby="blog-steps-heading">
              <h2 id="blog-steps-heading" className="blog-section-title">
                {t['blogpost.steps']}
              </h2>
              <ol className="blog-steps">
                {recipe.steps.map((step, index) => (
                  <li key={index} className="blog-step">
                    <span className="blog-step-number" aria-hidden="true">
                      {index + 1}
                    </span>
                    <div className="blog-step-body">
                      <p>{step.text}</p>
                      {step.image ? (
                        <img
                          className="blog-step-image"
                          src={step.image}
                          alt=""
                        />
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            </section>

            {recipe.author ? (
              <section
                className="blog-author-block"
                aria-label={t['blogpost.authorLabel']}
              >
                <p className="blog-author-name">{recipe.author.name}</p>
                <p className="blog-author-count">
                  {fill(t['blogpost.authorCount'], {
                    count: String(recipe.author_recipe_count),
                  })}
                </p>
                <Link
                  to={`/blog?author=${encodeURIComponent(recipe.author.id)}`}
                  className="blog-author-link"
                >
                  {t['blogpost.authorLink']}
                </Link>
              </section>
            ) : null}

            <div className="blog-actions">
              <button
                type="button"
                className={`btn ${liked ? 'btn-primary' : 'btn-outline'}`}
                aria-pressed={liked}
                onClick={toggleLike}
              >
                <HeartIcon filled={liked} />
                {liked ? t['blogpost.liked'] : t['blogpost.like']} · {likesCount}
              </button>
              <button
                type="button"
                className={`btn ${saved ? 'btn-primary' : 'btn-outline'}`}
                aria-pressed={saved}
                onClick={toggleSave}
              >
                <BookmarkIcon filled={saved} />
                {saved ? t['blogpost.saved'] : t['blogpost.save']}
              </button>
              <span className="blog-action-count">
                {fill(t['blogpost.commentCount'], {
                  count: String(recipe.comment_count),
                })}
              </span>
            </div>
            {actionError ? (
              <p className="blog-action-error" role="alert">
                {actionError}
              </p>
            ) : null}

            <section
              className="blog-comments"
              aria-labelledby="blog-comments-heading"
            >
              <h2 id="blog-comments-heading" className="blog-section-title">
                {fill(t['blogpost.commentsTitle'], {
                  count: String(recipe.comment_count),
                })}
              </h2>
              <p className="blog-comments-upcoming">{t['blogpost.commentsSoon']}</p>
            </section>

            {isLoggedIn() ? (
              <div className="blog-shopping-list">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={listBusy}
                  onClick={generateShoppingList}
                >
                  {t['blogpost.shoppingList']}
                </button>
                {listMessage ? (
                  <p className="blog-shopping-list-message" role="status">
                    {listMessage}
                  </p>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </main>
    </div>
  )
}
