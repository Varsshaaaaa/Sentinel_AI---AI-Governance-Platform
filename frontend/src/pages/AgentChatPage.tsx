import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { IconFlask, IconReplay } from '../components/icons'
import { Callout, ErrorState, LoadingState, PageHeader, Panel } from '../components/ui'
import { useAgentChat } from '../context/AgentChatContext'
import { useChatLlmStatus, useChatSuggestions, useChatTurn } from '../lib/api'
import type { ChatEvent, ChatSuggestionItem } from '../lib/types'

function dispositionClass(disp?: string): string {
  if (disp === 'allow' || disp === 'warn' || disp === 'audit_only') return 'chat-pill allow'
  if (disp === 'require_hitl') return 'chat-pill hitl'
  if (disp === 'block' || disp === 'deny') return 'chat-pill block'
  return 'chat-pill'
}

function SuggestionChips({
  items,
  variant,
  onPick,
}: {
  items: string[] | ChatSuggestionItem[]
  variant: 'default' | 'deny' | 'hitl'
  onPick: (text: string) => void
}) {
  return (
    <div className="chat-chips">
      {items.map((item) => {
        const text = typeof item === 'string' ? item : item.text
        const title = typeof item === 'string' ? undefined : `${item.expected ?? ''} — ${item.reason ?? ''}`
        return (
          <button
            key={text}
            type="button"
            className={`chat-chip chat-chip-${variant}`}
            title={title}
            onClick={() => onPick(text)}
          >
            {text}
          </button>
        )
      })}
    </div>
  )
}

function TracePanel({ events }: { events: ChatEvent[] }) {
  const route = events.find((e) => e.kind === 'route')
  const intent = events.find((e) => e.kind === 'tool_intent')
  const gov = events.find((e) => e.kind === 'governance')

  if (!route && !intent && !gov) {
    return (
      <p className="muted small">
        Send a message to see Cerebras route an agent, call a tool, and hit{' '}
        <code>POST /tool/intercept</code>.
      </p>
    )
  }

  return (
    <div className="chat-trace">
      {route ? (
        <div className="chat-trace-row">
          <strong>Routing</strong>
          <span>{route.agent_name}</span>
          <span className="chat-pill">{route.reason as string}</span>
        </div>
      ) : null}
      {intent ? (
        <div className="chat-trace-row">
          <strong>Tool</strong>
          <code className="small">
            {intent.tool_name}({JSON.stringify(intent.params ?? {})})
          </code>
          {gov ? <span className={dispositionClass(gov.disposition)}>{gov.disposition}</span> : null}
        </div>
      ) : null}
      {gov ? (
        <>
          <details className="chat-trace-details" open>
            <summary>Intercept request</summary>
            <pre>{JSON.stringify(gov.request ?? {}, null, 2)}</pre>
          </details>
          <details className="chat-trace-details" open>
            <summary>Intercept response · {gov.disposition}</summary>
            <pre>{JSON.stringify(gov.response ?? {}, null, 2)}</pre>
          </details>
        </>
      ) : null}
    </div>
  )
}

export function AgentChatPage() {
  const suggestions = useChatSuggestions()
  const llmStatus = useChatLlmStatus()
  const chatTurn = useChatTurn()
  const {
    sessionId,
    setSessionId,
    history,
    setHistory,
    activeAgent,
    setActiveAgent,
    input,
    setInput,
    messages,
    setMessages,
    lastEvents,
    setLastEvents,
    newSession,
  } = useAgentChat()
  const listRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  function pickSuggestion(text: string) {
    setInput(text)
  }

  async function submitMessage() {
    const message = input.trim()
    if (!message || chatTurn.isPending) return

    setMessages((prev) => [...prev, { role: 'user', content: message }])
    setInput('')

    try {
      const data = await chatTurn.mutateAsync({
        message,
        session_id: sessionId,
        history,
        active_agent: activeAgent,
      })

      if (!data.ok) {
        setMessages((prev) => [...prev, { role: 'error', content: data.error ?? 'Chat failed' }])
        return
      }

      if (data.session_id) setSessionId(data.session_id)
      if (data.agent_name) setActiveAgent(data.agent_name)
      if (data.history) setHistory(data.history)
      setLastEvents(data.events ?? [])
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply ?? '' }])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: err instanceof Error ? err.message : 'Network error' },
      ])
    }
  }

  if (suggestions.isLoading) {
    return (
      <section className="page-section">
        <LoadingState />
      </section>
    )
  }

  if (suggestions.isError) {
    return (
      <section className="page-section">
        <ErrorState>Could not load chat suggestions. Is the chat Lambda / API running?</ErrorState>
      </section>
    )
  }

  const sug = suggestions.data

  return (
    <section className="page-section agent-chat-page">
      <PageHeader
        eyebrow={
          <>
            <IconFlask width={13} height={13} /> Testing · Governed Agent Chat
          </>
        }
        title="Agent Chat"
        subtitle={
          <>
            An <strong>agent calling experience</strong> for governance testing — not a fully developed
            general-purpose chatbot. Use the sidebar scenarios to see real{' '}
            <code>POST /tool/intercept</code> outcomes (allow, block, deny, HITL). The governance pipeline
            is production-accurate; conversational replies may be simpler or less polished.
          </>
        }
        actions={
          <>
            <Link to={`/replay?session=${encodeURIComponent(sessionId)}`} className="btn sm secondary">
              <IconReplay width={14} height={14} /> Replay session
            </Link>
            <button type="button" className="btn sm secondary" onClick={newSession}>
              New session
            </button>
          </>
        }
      />

      {!llmStatus.data?.configured ? (
        <Callout variant="warn">
          Cerebras is not configured on the chat Lambda (<code>CEREBRAS_API_KEY</code>). Chat routing will fail
          until the key is set.
        </Callout>
      ) : null}

      <Callout>
        <strong>What this is:</strong> a governed agent-calling demo — pick a scenario, watch routing and
        tool intent, and verify intercept dispositions in the trace.{' '}
        <strong>What it is not:</strong> a polished end-user chatbot; NLU and multi-turn conversation are
        intentionally lightweight.{' '}
        <strong>What you can trust:</strong> governance decisions (WAF, policy, HITL) match the same API
        used in production — check HITL Queue, Violations, and Decision Replay after a run.
      </Callout>

      <div className="agent-chat-grid">
        <aside className="agent-chat-sidebar">
          <p className="muted small chat-sidebar-intro">
            Start here — each chip runs a known agent tool path through governance. These scenarios are the
            most reliable way to demo accurate allow, block, deny, and HITL results.
          </p>
          <Panel title="Try asking">
            <SuggestionChips items={sug?.try_asking ?? []} variant="default" onPick={pickSuggestion} />
          </Panel>
          <Panel title="Expect block / deny" className="chat-panel-deny">
            <SuggestionChips items={sug?.deny_block ?? []} variant="deny" onPick={pickSuggestion} />
          </Panel>
          <Panel title="Expect approval (HITL)" className="chat-panel-hitl">
            <SuggestionChips items={sug?.hitl ?? []} variant="hitl" onPick={pickSuggestion} />
          </Panel>
          <p className="muted small">
            Session <code>{sessionId}</code>
            {llmStatus.data?.model ? (
              <>
                {' '}
                · LLM <code>{llmStatus.data.model}</code>
              </>
            ) : null}
          </p>
        </aside>

        <Panel title="Conversation" className="agent-chat-main">
          <ul className="chat-message-list" ref={listRef}>
            {messages.map((msg, i) => (
              <li key={`${msg.role}-${i}`} className={`chat-message chat-message-${msg.role}`}>
                <div className="chat-bubble">{msg.content}</div>
              </li>
            ))}
            {chatTurn.isPending ? (
              <li className="chat-message chat-message-system">
                <div className="chat-bubble">Cerebras is routing and planning…</div>
              </li>
            ) : null}
          </ul>
          <form
            className="chat-composer"
            onSubmit={(e) => {
              e.preventDefault()
              void submitMessage()
            }}
          >
            <textarea
              rows={2}
              value={input}
              placeholder="Or type your own request — sidebar scenarios are recommended for accurate governance demos…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void submitMessage()
                }
              }}
            />
            <button type="submit" className="btn primary" disabled={chatTurn.isPending || !input.trim()}>
              Send
            </button>
          </form>
        </Panel>

        <Panel title="Governance trace">
          <TracePanel events={lastEvents} />
        </Panel>
      </div>
    </section>
  )
}
