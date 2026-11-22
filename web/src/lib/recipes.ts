/**
 * Recipe blog API client — talks to /api/v2/recipes (Phase 3).
 *
 * List + detail are PUBLIC. When the reader is logged in, the
 * requests carry the access token (via apiFetch, with refresh) so
 * the response includes the real `liked` / `saved` flags; when the
 * reader is anonymous -- or the session has expired -- the same
 * calls fall back to an unauthenticated fetch instead of failing
 * the public page (an expired token must never break /blog).
 */

import {
  ApiError,
  apiFetch,
  AuthExpiredError,
  getStoredHouseholdId,
  isLoggedIn,
} from './auth'

export interface RecipeAuthor {
  id: string
  name: string
}

export interface RecipeListItem {
  id: string
  title: string
  cover_image: string | null
  cook_time: number | null
  ingredient_count: number
  likes_count: number
  created_at: string | null
  author: RecipeAuthor | null
  source_url: string | null
  liked?: boolean
  saved?: boolean
}

export interface RecipeListResponse {
  items: RecipeListItem[]
  total: number
  limit: number
  offset: number
}

export interface RecipeIngredient {
  name: string
  quantity: number | null
  unit: string | null
}

export interface RecipeStep {
  text: string
  image: string | null
}

export interface RecipeDetail extends RecipeListItem {
  ingredients: RecipeIngredient[]
  steps: RecipeStep[]
  comment_count: number
  saved_count: number
  author_recipe_count: number
}

export interface LikeResponse {
  id: string
  likes_count: number
  liked: boolean
}

export interface SaveResponse {
  id: string
  saved: boolean
}

async function parseError(res: Response): Promise<ApiError> {
  const data = (await res.json().catch(() => null)) as {
    detail?: string
  } | null
  const message =
    typeof data?.detail === 'string' && data.detail.length > 0
      ? data.detail
      : `Request failed (${res.status})`
  return new ApiError(res.status, message)
}

async function publicGet<T>(path: string): Promise<T> {
  if (isLoggedIn()) {
    try {
      const res = await apiFetch(path, { method: 'GET' })
      if (!res.ok) throw await parseError(res)
      return (await res.json()) as T
    } catch (err) {
      // Session dead -> read as anonymous instead of breaking the
      // public page (apiFetch already cleared the dead tokens).
      if (!(err instanceof AuthExpiredError)) throw err
    }
  }
  const res = await fetch(path, { method: 'GET' })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

export function fetchRecipes(params: {
  ingredient?: string
  author?: string
  limit?: number
  offset?: number
}): Promise<RecipeListResponse> {
  const query = new URLSearchParams()
  if (params.ingredient) query.set('ingredient', params.ingredient)
  if (params.author) query.set('author', params.author)
  query.set('limit', String(params.limit ?? 20))
  query.set('offset', String(params.offset ?? 0))
  return publicGet<RecipeListResponse>(`/api/v2/recipes?${query}`)
}

export function fetchRecipe(id: string): Promise<RecipeDetail> {
  return publicGet<RecipeDetail>(
    `/api/v2/recipes/${encodeURIComponent(id)}`,
  )
}

async function postAction<T>(path: string): Promise<T> {
  const res = await apiFetch(path, { method: 'POST' })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

export function likeRecipe(id: string): Promise<LikeResponse> {
  return postAction<LikeResponse>(
    `/api/v2/recipes/${encodeURIComponent(id)}/like`,
  )
}

export function unlikeRecipe(id: string): Promise<LikeResponse> {
  return postAction<LikeResponse>(
    `/api/v2/recipes/${encodeURIComponent(id)}/unlike`,
  )
}

export function saveRecipe(id: string): Promise<SaveResponse> {
  return postAction<SaveResponse>(
    `/api/v2/recipes/${encodeURIComponent(id)}/save`,
  )
}

export function unsaveRecipe(id: string): Promise<SaveResponse> {
  return postAction<SaveResponse>(
    `/api/v2/recipes/${encodeURIComponent(id)}/unsave`,
  )
}

/** Create an open shopping list from a recipe (needs a household). */
export async function createShoppingListFromRecipe(
  recipeId: string,
): Promise<{ id: string }> {
  const householdId = getStoredHouseholdId()
  if (!householdId) {
    throw new ApiError(400, 'No household selected')
  }
  const res = await apiFetch('/api/v2/shopping-lists/from-recipe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      household_id: householdId,
      recipe_id: recipeId,
    }),
  })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as { id: string }
}

/** 2.0 -> "2", 0.5 -> "0.5", 100.50 -> "100.5" (no trailing zeros). */
export function formatQuantity(value: number): string {
  return String(value)
}

/** "2026-11-21T14:48:03Z" -> "2026-11-21" (date part only, as stored). */
export function formatDate(iso: string | null): string | null {
  if (!iso) return null
  return iso.slice(0, 10)
}

/**
 * Display name for a recipe source URL.
 *
 * The two seed sources use their own site titles (never invented);
 * any other source falls back to its hostname. The `www.` / `m.`
 * prefix is ignored when matching (the Chinese seed uses the mobile
 * host m.meishichina.com).
 */
export function sourceSiteName(sourceUrl: string): string {
  let hostname = ''
  try {
    hostname = new URL(sourceUrl).hostname.toLowerCase()
  } catch {
    return sourceUrl
  }
  const bare = hostname.replace(/^(www|m)\./, '')
  if (bare === 'monngonmoingay.com') return 'Món Ngon Mỗi Ngày'
  if (bare === 'meishichina.com') return '美食天下'
  return hostname
}
