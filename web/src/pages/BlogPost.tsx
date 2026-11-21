import { useParams } from 'react-router-dom'

/** Placeholder — the recipe article page is built in Wave 2. */
export function BlogPostPage() {
  const { id } = useParams()
  return (
    <main className="placeholder-page" style={{ padding: 24 }}>
      <h1>菜谱</h1>
      <p>Placeholder — the recipe article page is built in Wave 2.</p>
      <p>文章 ID：{id}</p>
    </main>
  )
}
