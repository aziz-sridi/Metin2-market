import { lazy, Suspense } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import './App.css'
import Layout from './components/Layout.jsx'

const HomePage = lazy(() => import('./pages/HomePage.jsx'))
const PriceHistoryPage = lazy(() => import('./pages/PriceHistoryPage.jsx'))
const EquipmentAnalysisPage = lazy(() => import('./pages/EquipmentAnalysisPage.jsx'))
const DealsPage = lazy(() => import('./pages/DealsPage.jsx'))
const AlertsPage = lazy(() => import('./pages/AlertsPage.jsx'))

function PageFallback() {
  return (
    <div className="flex min-h-64 items-center justify-center text-sm text-slate-500 dark:text-slate-400">
      Loading dashboard…
    </div>
  )
}

function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl py-20 text-center">
      <p className="text-sm font-semibold uppercase tracking-widest text-slate-500">404</p>
      <h1 className="mt-3 text-3xl font-bold">Page not found</h1>
      <p className="mt-3 text-slate-600 dark:text-slate-400">
        The market page you requested does not exist.
      </p>
      <Link className="mt-6 inline-block rounded-md bg-slate-900 px-4 py-2 text-white dark:bg-white dark:text-slate-900" to="/">
        Return to dashboard
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/price-history" element={<PriceHistoryPage />} />
          <Route path="/equipment" element={<EquipmentAnalysisPage />} />
          <Route path="/deals" element={<DealsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}
