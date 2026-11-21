import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { PublicOnly, RequireAuth } from './components/guards'
import { BlogPage } from './pages/Blog'
import { BlogPostPage } from './pages/BlogPost'
import { LandingPage } from './pages/Landing'
import { LoginPage } from './pages/Login'
import { NotFoundPage } from './pages/NotFound'
import { RegisterPage } from './pages/Register'
import { FridgePage } from './pages/app/Fridge'
import { MaintenancePage } from './pages/app/Maintenance'
import { MinePage } from './pages/app/Mine'
import { ReceiptDetailPage } from './pages/app/ReceiptDetail'
import { ReceiptsPage } from './pages/app/Receipts'
import { SpendingPage } from './pages/app/Spending'
import { TransactionsPage } from './pages/app/Transactions'
import { UploadPage } from './pages/app/Upload'

/**
 * Routes (reform plan §3.2):
 *   /            public landing (placeholder; Wave 2 builds it)
 *   /login       public (placeholder form in Wave 2)
 *   /register    public (placeholder form in Wave 2)
 *   /app/*       guarded — unauthenticated → /login?next=<path>
 *   /blog        public recipe list (placeholder; Wave 2)
 *   /blog/:id    public recipe article (placeholder; Wave 2)
 *   *            404 catch-all
 *
 * /app redirects to /app/upload (the Mini Program's post-login
 * destination, plan §3.2 Q2 decided) and the 首页 sidebar item points
 * to /app/upload. /app/recipes does NOT exist — recipes live at /blog
 * (plan §5.3); the sidebar 菜谱 item already points there.
 * /app/receipts and /app/receipts/:id are NOT in the sidebar; they are
 * reached from the upload page and from receipt rows.
 * /app/maintenance is NOT in the sidebar; it is linked from 我的.
 * Shopping lists are NOT built in this wave (no route in §3.2).
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/login"
        element={
          <PublicOnly>
            <LoginPage />
          </PublicOnly>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnly>
            <RegisterPage />
          </PublicOnly>
        }
      />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/app/upload" replace />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="fridge" element={<FridgePage />} />
        <Route path="transactions" element={<TransactionsPage />} />
        <Route path="spending" element={<SpendingPage />} />
        <Route path="maintenance" element={<MaintenancePage />} />
        <Route path="receipts" element={<ReceiptsPage />} />
        <Route path="receipts/:id" element={<ReceiptDetailPage />} />
        <Route path="mine" element={<MinePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="/blog" element={<BlogPage />} />
      <Route path="/blog/:id" element={<BlogPostPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
