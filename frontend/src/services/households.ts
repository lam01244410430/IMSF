/**
 * Households API — Phase 1 §5.1 (đối chiếu app/api/households.py).
 * GET /households → [{id, name, default_currency, timezone, locale,
 * created_at, role}]. POST /households {name} → 201 household (creator là owner).
 */
import { request } from './http'

export interface Household {
  id: string
  name: string
  default_currency: string
  timezone: string
  locale: string
  created_at: string | null
  role: string
}

export function listHouseholds(): Promise<Household[]> {
  return request<Household[]>('/households')
}

export function createHousehold(name: string): Promise<Household> {
  return request<Household>('/households', { method: 'POST', body: { name } })
}
