import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <main className="placeholder-page" style={{ padding: 24 }}>
      <h1>页面不存在</h1>
      <p>你要找的页面不存在。</p>
      <p>
        <Link to="/">回首页</Link>
      </p>
    </main>
  )
}
