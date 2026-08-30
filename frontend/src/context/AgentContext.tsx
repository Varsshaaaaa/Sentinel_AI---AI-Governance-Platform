import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

type AgentContextValue = {
  /** Currently selected agent id, or null for "all agents". */
  agentId: string | null
  setAgentId: (id: string | null) => void
}

const AgentContext = createContext<AgentContextValue | null>(null)

const STORAGE_KEY = 'sentinelai.selectedAgent'

export function AgentProvider({ children }: { children: ReactNode }) {
  const [agentId, setAgentIdState] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem(STORAGE_KEY) || null
  })

  const setAgentId = (id: string | null) => {
    setAgentIdState(id)
    if (typeof window !== 'undefined') {
      if (id) window.localStorage.setItem(STORAGE_KEY, id)
      else window.localStorage.removeItem(STORAGE_KEY)
    }
  }

  const value = useMemo(() => ({ agentId, setAgentId }), [agentId])
  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>
}

export function useAgent(): AgentContextValue {
  const ctx = useContext(AgentContext)
  if (!ctx) throw new Error('useAgent must be used within AgentProvider')
  return ctx
}
