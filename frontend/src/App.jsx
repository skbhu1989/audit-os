import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppProvider, useApp } from './context/AppContext'
import Shell from './components/Shell'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Engagements from './pages/Engagements'
import Dashboard from './pages/Dashboard'
import DataCentre from './pages/DataCentre'
import TrialBalance from './pages/TrialBalance'
import Gst from './pages/Gst'
import Tds from './pages/Tds'
import Payroll from './pages/Payroll'
import Bank from './pages/Bank'
import ApAr from './pages/ApAr'
import FixedAssets from './pages/FixedAssets'
import Inventory from './pages/Inventory'
import Loans from './pages/Loans'
import Investments from './pages/Investments'
import Intercompany from './pages/Intercompany'
import Risk from './pages/Risk'
import Exceptions from './pages/Exceptions'
import MonthEndClose from './pages/MonthEndClose'
import WorkingPapers from './pages/WorkingPapers'
import Caro from './pages/Caro'
import Ifc from './pages/Ifc'
import AiAssistant from './pages/AiAssistant'

function RequireAuth({ children }) {
  const { user } = useApp()
  if (!user) return <Navigate to="/login" replace />
  return children
}

function ShellRoute({ children }) {
  return (
    <RequireAuth>
      <Shell>{children}</Shell>
    </RequireAuth>
  )
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/engagements" element={<RequireAuth><Engagements /></RequireAuth>} />
          <Route path="/dashboard" element={<ShellRoute><Dashboard /></ShellRoute>} />
          <Route path="/data-centre" element={<ShellRoute><DataCentre /></ShellRoute>} />
          <Route path="/trial-balance" element={<ShellRoute><TrialBalance /></ShellRoute>} />
          <Route path="/gst" element={<ShellRoute><Gst /></ShellRoute>} />
          <Route path="/tds" element={<ShellRoute><Tds /></ShellRoute>} />
          <Route path="/payroll" element={<ShellRoute><Payroll /></ShellRoute>} />
          <Route path="/bank" element={<ShellRoute><Bank /></ShellRoute>} />
          <Route path="/ap-ar" element={<ShellRoute><ApAr /></ShellRoute>} />
          <Route path="/fixed-assets" element={<ShellRoute><FixedAssets /></ShellRoute>} />
          <Route path="/inventory" element={<ShellRoute><Inventory /></ShellRoute>} />
          <Route path="/loans" element={<ShellRoute><Loans /></ShellRoute>} />
          <Route path="/investments" element={<ShellRoute><Investments /></ShellRoute>} />
          <Route path="/intercompany" element={<ShellRoute><Intercompany /></ShellRoute>} />
          <Route path="/risk" element={<ShellRoute><Risk /></ShellRoute>} />
          <Route path="/exceptions" element={<ShellRoute><Exceptions /></ShellRoute>} />
          <Route path="/month-end-close" element={<ShellRoute><MonthEndClose /></ShellRoute>} />
          <Route path="/working-papers" element={<ShellRoute><WorkingPapers /></ShellRoute>} />
          <Route path="/caro" element={<ShellRoute><Caro /></ShellRoute>} />
          <Route path="/ifc" element={<ShellRoute><Ifc /></ShellRoute>} />
          <Route path="/ai-assistant" element={<ShellRoute><AiAssistant /></ShellRoute>} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
