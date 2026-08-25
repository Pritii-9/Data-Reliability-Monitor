import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Results from './pages/Results'
import AuditReport from './pages/AuditReport'
import { ToastContainer } from './components/Toast'
import Copilot from './components/Copilot'

export default function App() {
  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/results" element={<Results />} />
          <Route path="/audit" element={<AuditReport />} />
        </Routes>
      </main>
      <ToastContainer />
      <Copilot />
    </div>
  )
}
