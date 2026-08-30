import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { LoadingState } from './components/ui'

const AgentChatPage = lazy(() =>
  import('./pages/AgentChatPage').then((module) => ({ default: module.AgentChatPage })),
)
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })),
)
const AgentsPage = lazy(() =>
  import('./pages/AgentsPage').then((module) => ({ default: module.AgentsPage })),
)
const ReplayPage = lazy(() =>
  import('./pages/ReplayPage').then((module) => ({ default: module.ReplayPage })),
)
const GraphPage = lazy(() =>
  import('./pages/GraphPage').then((module) => ({ default: module.GraphPage })),
)
const PoliciesPage = lazy(() =>
  import('./pages/PoliciesPage').then((module) => ({ default: module.PoliciesPage })),
)
const WafPage = lazy(() =>
  import('./pages/WafPage').then((module) => ({ default: module.WafPage })),
)
const ViolationsPage = lazy(() =>
  import('./pages/ViolationsPage').then((module) => ({ default: module.ViolationsPage })),
)
const HitlPage = lazy(() =>
  import('./pages/HitlPage').then((module) => ({ default: module.HitlPage })),
)
const ObservabilityPage = lazy(() =>
  import('./pages/ObservabilityPage').then((module) => ({ default: module.ObservabilityPage })),
)

function App() {
  return (
    <Suspense fallback={<div className="content-shell"><LoadingState /></div>}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/waf" element={<WafPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="/hitl" element={<HitlPage />} />
          <Route path="/violations" element={<ViolationsPage />} />
          <Route path="/replay" element={<ReplayPage />} />
          <Route path="/observability" element={<ObservabilityPage />} />
          <Route path="/agent-chat" element={<AgentChatPage />} />
          <Route path="/simulator" element={<Navigate to="/waf" replace />} />
          <Route path="/evaluator" element={<Navigate to="/dashboard" replace />} />
          <Route path="/timeline" element={<Navigate to="/observability" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default App
