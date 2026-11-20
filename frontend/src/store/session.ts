/**
 * Session store — Zustand client state (§8.7).
 * user + households[] + currentHouseholdId + isLoggedIn. Token nằm trong
 * Taro storage (services/auth.ts), KHÔNG nằm trong store này ngoài bản copy
 * in-memory là isLoggedIn.
 */
import { create } from 'zustand'
import { getStoredHouseholdId, setStoredHouseholdId } from '../services/auth'
import type { AuthUser, HouseholdSummary } from '../services/auth'

interface SessionState {
  user: AuthUser | null
  households: HouseholdSummary[]
  currentHouseholdId: string | null
  isLoggedIn: boolean
  setSession: (user: AuthUser, households: HouseholdSummary[]) => void
  setCurrentHousehold: (id: string) => void
  clearSession: () => void
}

export const useSessionStore = create<SessionState>()((set) => ({
  user: null,
  households: [],
  // last-used household từ storage (nếu có) — khởi tạo khi app load.
  currentHouseholdId: getStoredHouseholdId(),
  isLoggedIn: false,
  setSession: (user, households) => {
    // Ưu tiên last-used từ storage, nếu không thì household đầu tiên (§8.4).
    const current = getStoredHouseholdId() ?? households[0]?.id ?? null
    if (current) setStoredHouseholdId(current)
    set({ user, households, isLoggedIn: true, currentHouseholdId: current })
  },
  setCurrentHousehold: (id) => {
    setStoredHouseholdId(id)
    set({ currentHouseholdId: id })
  },
  clearSession: () => set({ user: null, households: [], isLoggedIn: false, currentHouseholdId: null }),
}))
