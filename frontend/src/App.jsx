import { Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import DashboardPage from './pages/DashboardPage'
import HubPage from './pages/HubPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/hub" element={<HubPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
