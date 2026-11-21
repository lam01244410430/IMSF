import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PublicHeader } from '../components/PublicHeader'
import { ApiError, isLoggedIn } from '../lib/auth'
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
 * - Steps: numbered list 1, 2, 3... (numbers in accent #C2410C
 *   18px/700, no icon tiles), one short paragraph per step + step
 *   image only if the author provided one (never a fake illustration).
 * - Author block: name + real count of their recipes + link
 *   /blog?author=<id>.
 * - 点赞 / 收藏 with real counts. NOT logged in -> clicking goes to
 *   /login with a clear message (navigation state `notice`, which the
 *   Wave 2 login form renders) -- never silently does nothing.
 * - Comment count shown (real); the comment area shows
 *   评论功能即将上线 (comments DEFERRED -- no comment form).
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
      state: { notice: `请先登录，登录后即可${action}。` },
    })
  }

  async function toggleLike() {
    if (!recipe || !id) return
    if (!isLoggedIn()) {
      requireLogin('点赞')
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
      setActionError('操作失败，请稍后再试。')
    }
  }

  async function toggleSave() {
    if (!recipe || !id) return
    if (!isLoggedIn()) {
      requireLogin('收藏')
      return
    }
    setActionError(null)
    try {
      const result = saved ? await unsaveRecipe(id) : await saveRecipe(id)
      setSaved(result.saved)
    } catch {
      setActionError('操作失败，请稍后再试。')
    }
  }

  async function generateShoppingList() {
    if (!recipe || !id) return
    setListBusy(true)
    setListMessage(null)
    try {
      await createShoppingListFromRecipe(id)
      setListMessage('购物清单已生成。')
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setListMessage('已经有一张未完成的购物清单。')
      } else {
        setListMessage('生成购物清单失败，请稍后再试。')
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
      metaParts.push(`烹饪时间 ${recipe.cook_time}分钟`)
    }
    metaParts.push(`${recipe.ingredient_count}种食材`)
    metaParts.push(`${likesCount}个赞 · ${recipe.saved_count}个收藏 · ${recipe.comment_count}条评论`)
  }

  return (
    <div>
      <PublicHeader />
      <main className="blog-article">
        {!id || notFound ? (
          <div className="blog-error" role="alert">
            <p>未找到这道菜谱，它可能已被删除或尚未发布。</p>
            <Link to="/blog" className="btn btn-primary">
              返回菜谱列表
            </Link>
          </div>
        ) : loading ? (
          <div className="blog-article-skeleton" aria-label="加载中">
            <div className="blog-skeleton-cover" />
            <div className="blog-skeleton-line blog-skeleton-title" />
            <div className="blog-skeleton-line blog-skeleton-meta" />
          </div>
        ) : error || recipe === null ? (
          <div className="blog-error" role="alert">
            <p>加载失败，请检查网络后重试。</p>
            <button type="button" className="btn btn-primary" onClick={retry}>
              重试
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
            <p className="blog-article-meta">{metaParts.join(' · ')}</p>

            <section aria-labelledby="blog-ingredients-heading">
              <h2 id="blog-ingredients-heading" className="blog-section-title">
                食材
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
                步骤
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
                aria-label="作者"
              >
                <p className="blog-author-name">{recipe.author.name}</p>
                <p className="blog-author-count">
                  已发布 {recipe.author_recipe_count} 个菜谱
                </p>
                <Link
                  to={`/blog?author=${encodeURIComponent(recipe.author.id)}`}
                  className="blog-author-link"
                >
                  查看TA的其他菜谱
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
                {liked ? '已点赞' : '点赞'} · {likesCount}
              </button>
              <button
                type="button"
                className={`btn ${saved ? 'btn-primary' : 'btn-outline'}`}
                aria-pressed={saved}
                onClick={toggleSave}
              >
                <BookmarkIcon filled={saved} />
                {saved ? '已收藏' : '收藏'}
              </button>
              <span className="blog-action-count">
                {recipe.comment_count}条评论
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
                评论（{recipe.comment_count}）
              </h2>
              <p className="blog-comments-upcoming">评论功能即将上线</p>
            </section>

            {isLoggedIn() ? (
              <div className="blog-shopping-list">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={listBusy}
                  onClick={generateShoppingList}
                >
                  用这道菜生成购物清单
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
