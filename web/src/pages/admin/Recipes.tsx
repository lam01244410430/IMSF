/**
 * Admin Recipes (/admin/recipes) — Dashboard Phase C (plan §4.4,
 * contract §2 #10–#12).
 *
 * Seed-recipe management: the list includes drafts + hidden (unlike
 * the public list, which shows published only). Create/edit a seed
 * draft; publish / hide / republish. Hiding is reversible — likes,
 * saves and the recipe identity are preserved server-side.
 *
 * Honest empty state: "No recipes yet." — no invented moderation
 * activity. Community approval states (pending/rejected) are a
 * later phase and are NOT in this UI.
 */
import { useEffect, useState } from 'react'
import {
  createAdminRecipe,
  listAdminRecipes,
  patchAdminRecipe,
  type AdminRecipe,
  type AdminRecipePatchInput,
  type AdminRecipeStatus,
} from '../../lib/admin'
import { formatDateTime } from '../../lib/format'
import { useLanguage } from '../../lib/i18n'
import { StatusChip } from '../../components/StatusChip'
import { AdminLoadError, AdminPager } from './common'

const PAGE_SIZE = 20

interface RecipeForm {
  title: string
  description: string
  source_url: string
  category: string
  language: string
  difficulty: string
  taste: string
  slug: string
  author: string
  cover_image: string
  cook_time: string
  steps: string
}

const EMPTY_FORM: RecipeForm = {
  title: '',
  description: '',
  source_url: '',
  category: '',
  language: '',
  difficulty: '',
  taste: '',
  slug: '',
  author: '',
  cover_image: '',
  cook_time: '',
  steps: '',
}

function formToCreateBody(form: RecipeForm) {
  return {
    title: form.title.trim(),
    description: form.description.trim() || null,
    source_url: form.source_url.trim() || null,
    category: form.category.trim() || null,
    language: form.language || null,
    difficulty: form.difficulty.trim() || null,
    taste: form.taste.trim() || null,
    slug: form.slug.trim() || null,
    author: form.author.trim() || null,
    cover_image: form.cover_image.trim() || null,
    cook_time: form.cook_time.trim() === '' ? null : Number(form.cook_time),
    steps_json: form.steps
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s !== ''),
  }
}

export function AdminRecipesPage() {
  const { t, lang } = useLanguage()
  const [statusFilter, setStatusFilter] = useState<'' | AdminRecipeStatus>('')
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<AdminRecipe[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  const [showForm, setShowForm] = useState(false)
  // Editing id only — there is no GET-one-recipe endpoint, so the
  // edit form is prefilled from the LIST row and the PATCH sends
  // ONLY the fields the editor actually touched (see `touched`):
  // sending the full allowlist would overwrite the recipe's
  // description / steps / cook time with blanks.
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<RecipeForm>(EMPTY_FORM)
  const [touched, setTouched] = useState<Set<keyof RecipeForm>>(new Set())
  const [titleError, setTitleError] = useState(false)
  const [saveError, setSaveError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    listAdminRecipes({
      status: statusFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (!cancelled) {
          setItems(page.items)
          setTotal(page.total)
        }
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [statusFilter, offset, attempt])

  const refresh = () => setAttempt((n) => n + 1)

  const statusChip = (status: AdminRecipeStatus) => {
    switch (status) {
      case 'published':
        return <StatusChip tone="success" label={t['admin.recipesPublished']} />
      case 'hidden':
        return <StatusChip tone="neutral" label={t['admin.recipesHidden']} />
      default:
        return <StatusChip tone="warning" label={t['admin.recipesDraft']} />
    }
  }

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setTouched(new Set())
    setTitleError(false)
    setSaveError(false)
    setShowForm(true)
  }

  const openEdit = (recipe: AdminRecipe) => {
    setEditingId(recipe.id)
    setForm({
      ...EMPTY_FORM,
      title: recipe.title,
      author: recipe.author ?? '',
      source_url: recipe.source_url ?? '',
      category: recipe.category ?? '',
      language: recipe.language ?? '',
    })
    // Prefilled from the list row, so these five count as untouched:
    // editing them marks them touched, leaving them alone sends
    // nothing for them.
    setTouched(new Set())
    setTitleError(false)
    setSaveError(false)
    setShowForm(true)
  }

  const setStatus = (recipe: AdminRecipe, status: AdminRecipeStatus) => {
    setActionError(false)
    patchAdminRecipe(recipe.id, { status })
      .then(() => refresh())
      .catch(() => setActionError(true))
  }

  const submitForm = () => {
    if (form.title.trim() === '' && (editingId === null || touched.has('title'))) {
      setTitleError(true)
      return
    }
    setTitleError(false)
    setSaveError(false)
    setSaving(true)
    const done = () => {
      setSaving(false)
      setShowForm(false)
      setEditingId(null)
      refresh()
    }
    const onFail = () => {
      setSaving(false)
      setSaveError(true)
    }
    if (editingId !== null) {
      // PATCH only touched fields — see the `editingId` comment.
      const full = formToCreateBody(form)
      const patch: AdminRecipePatchInput = {}
      const pick = (field: keyof RecipeForm, key: keyof typeof full) => {
        if (touched.has(field)) {
          ;(patch as Record<string, unknown>)[key] = full[key]
        }
      }
      pick('title', 'title')
      pick('description', 'description')
      pick('source_url', 'source_url')
      pick('category', 'category')
      pick('language', 'language')
      pick('difficulty', 'difficulty')
      pick('taste', 'taste')
      pick('slug', 'slug')
      pick('author', 'author')
      pick('cover_image', 'cover_image')
      pick('cook_time', 'cook_time')
      if (touched.has('steps')) patch.steps_json = full.steps_json
      patchAdminRecipe(editingId, patch).then(done).catch(onFail)
    } else {
      createAdminRecipe(formToCreateBody(form)).then(done).catch(onFail)
    }
  }

  const setField = (field: keyof RecipeForm, value: string) => {
    setForm((f) => ({ ...f, [field]: value }))
    setTouched((prev) => new Set(prev).add(field))
  }

  return (
    <div className="page">
      <h1 className="page-title">{t['admin.recipesTitle']}</h1>
      <div className="admin-filters">
        <label className="form-field admin-filter-field" htmlFor="admin-recipes-status">
          {t['admin.recipesStatus']}
          <select
            id="admin-recipes-status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as '' | AdminRecipeStatus)
              setOffset(0)
            }}
          >
            <option value="">{t['admin.usersAll']}</option>
            <option value="draft">{t['admin.recipesDraft']}</option>
            <option value="published">{t['admin.recipesPublished']}</option>
            <option value="hidden">{t['admin.recipesHidden']}</option>
          </select>
        </label>
        <div className="admin-filter-actions">
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            {t['admin.recipesNew']}
          </button>
        </div>
      </div>

      {showForm && (
        <section className="admin-form-panel" aria-label={editingId !== null ? t['admin.recipesEditTitle'] : t['admin.recipesCreateTitle']}>
          <h2>{editingId !== null ? t['admin.recipesEditTitle'] : t['admin.recipesCreateTitle']}</h2>
          {saveError && <p className="page-error">{t['admin.recipesSaveFailed']}</p>}
          <label className="form-field" htmlFor="admin-recipe-title">
            {t['admin.recipesFieldTitle']}
            <input
              id="admin-recipe-title"
              type="text"
              value={form.title}
              onChange={(e) => setField('title', e.target.value)}
            />
          </label>
          {titleError && <p className="page-error">{t['admin.recipesTitleRequired']}</p>}
          <label className="form-field" htmlFor="admin-recipe-description">
            {t['admin.recipesDescription']}
            <input
              id="admin-recipe-description"
              type="text"
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
            />
          </label>
          <div className="admin-form-row">
            <label className="form-field" htmlFor="admin-recipe-author">
              {t['admin.recipesAuthor']}
              <input
                id="admin-recipe-author"
                type="text"
                value={form.author}
                onChange={(e) => setField('author', e.target.value)}
              />
            </label>
            <label className="form-field" htmlFor="admin-recipe-source">
              {t['admin.recipesSource']}
              <input
                id="admin-recipe-source"
                type="url"
                value={form.source_url}
                onChange={(e) => setField('source_url', e.target.value)}
              />
            </label>
          </div>
          <div className="admin-form-row">
            <label className="form-field" htmlFor="admin-recipe-category">
              {t['admin.recipesCategory']}
              <input
                id="admin-recipe-category"
                type="text"
                value={form.category}
                onChange={(e) => setField('category', e.target.value)}
              />
            </label>
            <label className="form-field" htmlFor="admin-recipe-language">
              {t['admin.recipesLanguage']}
              <select
                id="admin-recipe-language"
                value={form.language}
                onChange={(e) => setField('language', e.target.value)}
              >
                <option value="">—</option>
                <option value="zh">中文</option>
                <option value="vi">Tiếng Việt</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>
          <div className="admin-form-row">
            <label className="form-field" htmlFor="admin-recipe-difficulty">
              {t['admin.recipesDifficulty']}
              <input
                id="admin-recipe-difficulty"
                type="text"
                value={form.difficulty}
                onChange={(e) => setField('difficulty', e.target.value)}
              />
            </label>
            <label className="form-field" htmlFor="admin-recipe-taste">
              {t['admin.recipesTaste']}
              <input
                id="admin-recipe-taste"
                type="text"
                value={form.taste}
                onChange={(e) => setField('taste', e.target.value)}
              />
            </label>
          </div>
          <div className="admin-form-row">
            <label className="form-field" htmlFor="admin-recipe-slug">
              {t['admin.recipesSlug']}
              <input
                id="admin-recipe-slug"
                type="text"
                value={form.slug}
                onChange={(e) => setField('slug', e.target.value)}
              />
            </label>
            <label className="form-field" htmlFor="admin-recipe-cooktime">
              {t['admin.recipesCookTime']}
              <input
                id="admin-recipe-cooktime"
                type="number"
                min="0"
                value={form.cook_time}
                onChange={(e) => setField('cook_time', e.target.value)}
              />
            </label>
          </div>
          <label className="form-field" htmlFor="admin-recipe-cover">
            {t['admin.recipesCover']}
            <input
              id="admin-recipe-cover"
              type="url"
              value={form.cover_image}
              onChange={(e) => setField('cover_image', e.target.value)}
            />
          </label>
          <label className="form-field" htmlFor="admin-recipe-steps">
            {t['admin.recipesSteps']}
            <textarea
              id="admin-recipe-steps"
              rows={5}
              value={form.steps}
              onChange={(e) => setField('steps', e.target.value)}
            />
          </label>
          <div className="admin-confirm-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving || (editingId !== null && touched.size === 0)}
              onClick={submitForm}
            >
              {t['admin.save']}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={saving}
              onClick={() => {
                setShowForm(false)
                setEditingId(null)
              }}
            >
              {t['admin.cancel']}
            </button>
          </div>
        </section>
      )}

      {actionError && <p className="page-error">{t['admin.userActionFailed']}</p>}
      {error ? (
        <AdminLoadError onRetry={refresh} />
      ) : loading ? (
        <p className="page-note">{t['admin.loading']}</p>
      ) : items.length === 0 ? (
        <p className="page-empty">{t['admin.recipesEmpty']}</p>
      ) : (
        <>
          <div className="tx-table-wrap">
            <table className="tx-table">
              <thead>
                <tr>
                  <th>{t['admin.recipesFieldTitle']}</th>
                  <th>{t['admin.recipesStatus']}</th>
                  <th>{t['admin.recipesAuthor']}</th>
                  <th>{t['admin.recipesCategory']}</th>
                  <th>{t['admin.recipesUpdated']}</th>
                  <th>{t['admin.edit']}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {r.title}
                      {r.source_url ? (
                        <>
                          {' · '}
                          <a href={r.source_url} target="_blank" rel="noreferrer">
                            {t['admin.recipesSource']}
                          </a>
                        </>
                      ) : null}
                    </td>
                    <td>{statusChip(r.status)}</td>
                    <td>{r.author ?? '—'}</td>
                    <td>{r.category ?? '—'}</td>
                    <td>{formatDateTime(r.updated_at, lang)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => openEdit(r)}
                      >
                        {t['admin.edit']}
                      </button>
                      {r.status !== 'published' && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setStatus(r, 'published')}
                        >
                          {r.status === 'hidden'
                            ? t['admin.recipesRepublish']
                            : t['admin.recipesPublish']}
                        </button>
                      )}
                      {r.status === 'published' && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setStatus(r, 'hidden')}
                        >
                          {t['admin.recipesHide']}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <AdminPager total={total} offset={offset} limit={PAGE_SIZE} onPage={setOffset} />
        </>
      )}
    </div>
  )
}
