import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { PublicOnly, RequireAuth } from './components/guards'
import { BlogPage } from './pages/Blog'
import { BlogPostPage } from './pages/BlogPost'
import { LandingPage } from './pages/Landing'
import { LegalPage } from './pages/Legal'
import { LoginPage } from './pages/Login'
import { NotFoundPage } from './pages/NotFound'
import { RegisterPage } from './pages/Register'
import { AppHomePage } from './pages/app/AppHome'
import { FridgePage } from './pages/app/Fridge'
import { MinePage } from './pages/app/Mine'
import { SpendingPage } from './pages/app/Spending'
import { TransactionsPage } from './pages/app/Transactions'
import { UploadPage } from './pages/app/Upload'
import { LanguageProvider } from './lib/LanguageProvider'

/**
 * Routes (reform plan §3.2):
 *   /            public landing (Wave 2: hero, trust, features,
 *                how-it-works, FAQ, reviews, footer)
 *   /login       public email login (Wave 2)
 *   /register    public email registration (Wave 2)
 *   /app/*       guarded — unauthenticated → /login?next=<path>
 *   /blog        public recipe list (placeholder; Wave 2)
 *   /blog/:id    public recipe article (placeholder; Wave 2)
 *   /privacy /terms /contact — honest placeholder pages (§4.8):
 *                "being written", no fabricated legal text.
 *   *            404 catch-all
 *
 * /app redirects to /app/upload (the Mini Program's post-login
 * destination, plan §3.2). /app/recipes does NOT exist — recipes live
 * at /blog (plan §5.3). NOTE (Wave 1): /app currently renders the
 * 首页 placeholder instead of redirecting to /app/upload, so the 首页
 * nav item keeps its active state; the redirect is a Wave 2 decision
 * with the real home page.
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
        <Route index element={<AppHomePage />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="fridge" element={<FridgePage />} />
        <Route path="transactions" element={<TransactionsPage />} />
        <Route path="spending" element={<SpendingPage />} />
        <Route path="mine" element={<MinePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="/blog" element={<BlogPage />} />
      <Route path="/blog/:id" element={<BlogPostPage />} />
      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
      <Route path="/terms" element={<LegalPage kind="terms" />} />
      <Route path="/contact" element={<LegalPage kind="contact" />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </LanguageProvider>
  )
}
