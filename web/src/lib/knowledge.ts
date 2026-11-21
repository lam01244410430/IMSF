/**
 * Knowledge search client — GET /api/v2/knowledge/search (Phase 2
 * design §5.1, §7.2; backend `app/api/knowledge.py`).
 *
 * Returns [{title, source, content, score}] from the RAG lookup over
 * knowledge_documents; [] when nothing clears the 0.35 similarity
 * threshold — the client shows "don't know", a shelf life is never
 * fabricated. The endpoint requires JWT auth (no household scope:
 * knowledge_documents are global reference data).
 */
import { apiGetJson } from './auth'

export interface KnowledgeResult {
  title: string
  source: string
  content: string
  score: number
}

export function searchKnowledge(q: string): Promise<KnowledgeResult[]> {
  return apiGetJson<KnowledgeResult[]>(
    `/api/v2/knowledge/search?q=${encodeURIComponent(q)}&k=5`,
  )
}
