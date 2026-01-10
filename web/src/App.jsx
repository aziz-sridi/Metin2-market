import { NavLink, Route, Routes } from 'react-router-dom'
import './App.css'
import Layout from './components/Layout.jsx'

import HomePage from './pages/HomePage.jsx'
import PriceHistoryPage from './pages/PriceHistoryPage.jsx'
import EquipmentAnalysisPage from './pages/EquipmentAnalysisPage.jsx'
import DealsPage from './pages/DealsPage.jsx'
import AlertsPage from './pages/AlertsPage.jsx'

export default function App() {
  return (
    <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/price-history" element={<PriceHistoryPage />} />
          <Route path="/equipment" element={<EquipmentAnalysisPage />} />
          <Route path="/deals" element={<DealsPage />} />
        </Routes>
    </Layout>
  )
}
