import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type SetStateAction,
} from 'react'
import type { ChatEvent } from '../lib/types'

export type ChatMessage = { role: string; content: string }

type AgentChatState = {
  sessionId: string
  history: ChatMessage[]
  activeAgent: string | null
  input: string
  messages: ChatMessage[]
  lastEvents: ChatEvent[]
}

type AgentChatContextValue = AgentChatState & {
  setSessionId: (id: string) => void
  setHistory: (history: ChatMessage[]) => void
  setActiveAgent: (agent: string | null) => void
  setInput: (value: string) => void
  setMessages: (updater: SetStateAction<ChatMessage[]>) => void
  setLastEvents: (events: ChatEvent[]) => void
  newSession: () => void
}

const STORAGE_KEY = 'sentinelai.agentChat'

const INITIAL_SYSTEM_MESSAGE: ChatMessage = {
  role: 'system',
  content:
    'Agent calling demo — try the sidebar scenarios. Every tool call goes through governance intercept; free-form chat is limited.',
}

function createSessionId(): string {
  return `chat-${crypto.randomUUID().slice(0, 10)}`
}

function defaultState(): AgentChatState {
  return {
    sessionId: createSessionId(),
    history: [],
    activeAgent: null,
    input: '',
    messages: [INITIAL_SYSTEM_MESSAGE],
    lastEvents: [],
  }
}

function loadState(): AgentChatState {
  if (typeof window === 'undefined') return defaultState()
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultState()
    const parsed = JSON.parse(raw) as Partial<AgentChatState>
    if (!parsed.sessionId || !Array.isArray(parsed.messages)) return defaultState()
    return {
      sessionId: parsed.sessionId,
      history: Array.isArray(parsed.history) ? parsed.history : [],
      activeAgent: parsed.activeAgent ?? null,
      input: typeof parsed.input === 'string' ? parsed.input : '',
      messages: parsed.messages.length > 0 ? parsed.messages : [INITIAL_SYSTEM_MESSAGE],
      lastEvents: Array.isArray(parsed.lastEvents) ? parsed.lastEvents : [],
    }
  } catch {
    return defaultState()
  }
}

const AgentChatContext = createContext<AgentChatContextValue | null>(null)

export function AgentChatProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AgentChatState>(loadState)

  useEffect(() => {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  }, [state])

  const setSessionId = useCallback((sessionId: string) => {
    setState((prev) => ({ ...prev, sessionId }))
  }, [])

  const setHistory = useCallback((history: ChatMessage[]) => {
    setState((prev) => ({ ...prev, history }))
  }, [])

  const setActiveAgent = useCallback((activeAgent: string | null) => {
    setState((prev) => ({ ...prev, activeAgent }))
  }, [])

  const setInput = useCallback((input: string) => {
    setState((prev) => ({ ...prev, input }))
  }, [])

  const setMessages = useCallback((updater: SetStateAction<ChatMessage[]>) => {
    setState((prev) => ({
      ...prev,
      messages: typeof updater === 'function' ? updater(prev.messages) : updater,
    }))
  }, [])

  const setLastEvents = useCallback((lastEvents: ChatEvent[]) => {
    setState((prev) => ({ ...prev, lastEvents }))
  }, [])

  const newSession = useCallback(() => {
    setState({
      sessionId: createSessionId(),
      history: [],
      activeAgent: null,
      input: '',
      lastEvents: [],
      messages: [
        {
          role: 'system',
          content:
            'New session. Use the sidebar scenarios to exercise allow, block/deny, and HITL — that is where governance is most reliable.',
        },
      ],
    })
  }, [])

  const value = useMemo(
    () => ({
      ...state,
      setSessionId,
      setHistory,
      setActiveAgent,
      setInput,
      setMessages,
      setLastEvents,
      newSession,
    }),
    [state, setSessionId, setHistory, setActiveAgent, setInput, setMessages, setLastEvents, newSession],
  )

  return <AgentChatContext.Provider value={value}>{children}</AgentChatContext.Provider>
}

export function useAgentChat(): AgentChatContextValue {
  const ctx = useContext(AgentChatContext)
  if (!ctx) throw new Error('useAgentChat must be used within AgentChatProvider')
  return ctx
}
