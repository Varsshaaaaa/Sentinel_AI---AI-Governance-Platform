import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDeployCopilotPolicy,
  useGeneratePolicy,
  usePolicies,
  usePolicy,
  usePolicySimulation,
} from '../lib/api'
import { Callout, EmptyState, ErrorState, Kpi, Panel, PageHeader, Tabs } from '../components/ui'
import { IconFlask, IconScroll } from '../components/icons'
import type { PolicySimulationResult } from '../lib/types'

type TabId = 'browse' | 'copilot'

const EXAMPLE_PROMPTS = [
  'Block finance agent from deleting more than 100 records',
  'Require HITL for external emails outside company.com',
  'Suspend session after 3 policy violations',
  'Require HITL for data writes outside business hours (9 AM – 6 PM)',
]

function actionBadgeClass(action: string): string {
  const a = action.toLowerCase()
  if (a.includes('block') || a.includes('suspend') || a.includes('deny')) return 'status-red'
  if (a.includes('hitl') || a.includes('warn') || a.includes('apply')) return 'status-amber'
  return 'status-green'
}

function describeCondition(when: unknown): string {
  if (!when || typeof when !== 'object') return String(when ?? 'always')
  try {
    return JSON.stringify(when)
  } catch {
    return String(when)
  }
}

function BrowseTab({
  selectedPolicyId,
  onSelectPolicy,
}: {
  selectedPolicyId: string | null
  onSelectPolicy: (id: string) => void
}) {
  const policies = usePolicies()
  const policyDetail = usePolicy(selectedPolicyId)

  useEffect(() => {
    if (!selectedPolicyId && policies.data?.policies.length) {
      onSelectPolicy(policies.data.policies[0].policy_id)
    }
  }, [policies.data, onSelectPolicy, selectedPolicyId])

  const selectedPolicy = useMemo(() => policyDetail.data?.policy, [policyDetail.data])
  const policyList = policies.data?.policies ?? []

  return (
    <div className="two-column">
      <Panel title="Deployed policies" icon={<IconScroll width={18} height={18} />}>
        {policyList.length === 0 ? (
          <EmptyState title="No policies deployed" hint="Use Policy Copilot to generate and deploy your first policy." />
        ) : (
          <div className="stack-list">
            {policyList.map((policy) => (
              <button
                key={policy.policy_id}
                type="button"
                className={selectedPolicyId === policy.policy_id ? 'list-button active' : 'list-button'}
                onClick={() => onSelectPolicy(policy.policy_id)}
              >
                <div style={{ minWidth: 0 }}>
                  <strong>{policy.name}</strong>
                  <p className="muted small" style={{ margin: '2px 0 0' }}>
                    {policy.rules.length} rules{policy.inherits ? ` · inherits ${policy.inherits}` : ''}
                  </p>
                </div>
                <span className="badge status-active">{policy.status}</span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Policy detail" icon={<IconScroll width={18} height={18} />}>
        {selectedPolicy ? (
          <>
            <dl className="detail-list">
              <div><dt>Policy ID</dt><dd className="mono small">{selectedPolicy.policy_id}</dd></div>
              <div><dt>Inheritance</dt><dd>{selectedPolicy.inherits || 'None'}</dd></div>
              <div><dt>Status</dt><dd><span className="badge status-active">{selectedPolicy.status}</span></dd></div>
              <div><dt>Rules</dt><dd>{selectedPolicy.rules.length}</dd></div>
            </dl>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr><th>Rule</th><th>Priority</th><th>Condition</th><th>Action</th></tr>
                </thead>
                <tbody>
                  {selectedPolicy.rules.map((rule) => {
                    const action = String(rule.then.action ?? 'n/a')
                    return (
                      <tr key={rule.name}>
                        <td>{rule.name}</td>
                        <td>{rule.priority}</td>
                        <td className="mono small muted" style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={describeCondition(rule.when)}>
                          {describeCondition(rule.when)}
                        </td>
                        <td><span className={`badge ${actionBadgeClass(action)}`}>{action}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <EmptyState title="Select a policy" hint="Choose a policy to inspect its rules, conditions, and inheritance." />
        )}
      </Panel>
    </div>
  )
}

function SimulationSummary({ simulation }: { simulation: PolicySimulationResult }) {
  const details = Array.isArray(simulation.details) ? simulation.details : []
  const totalActions = Number(simulation.total_actions ?? 0)
  const wouldBlock = Number(simulation.would_block ?? 0)
  const wouldHitl = Number(simulation.would_hitl ?? 0)
  const riskScore = Number(simulation.risk_improvement_score ?? 0)

  return (
    <>
      <div className="kpi-grid" style={{ marginTop: 12 }}>
        <Kpi label="Actions replayed" value={totalActions} />
        <Kpi label="Would block" value={wouldBlock} />
        <Kpi label="Would HITL" value={wouldHitl} />
        <Kpi label="Risk score" value={riskScore} hint="Sandbox estimate" />
      </div>
      {details.length > 0 ? (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr><th>Session</th><th>Tool</th><th>Old</th><th>New</th><th>Rules</th></tr>
            </thead>
            <tbody>
              {details.slice(0, 12).map((row, index) => {
                const detail = row as Record<string, unknown>
                const rules = Array.isArray(detail.matched_rules) ? detail.matched_rules.join(', ') : '—'
                return (
                  <tr key={`${detail.session_id}-${detail.step_sequence}-${index}`}>
                    <td className="mono small">{String(detail.session_id ?? '—')}</td>
                    <td>{String(detail.tool ?? '—')}</td>
                    <td><span className="badge status-green">{String(detail.old_action ?? '—')}</span></td>
                    <td><span className={`badge ${actionBadgeClass(String(detail.new_action ?? ''))}`}>{String(detail.new_action ?? '—')}</span></td>
                    <td className="mono small muted">{rules}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {details.length > 12 ? <p className="muted small" style={{ marginTop: 8 }}>+{details.length - 12} more changed decisions</p> : null}
        </div>
      ) : (
        <p className="muted small" style={{ marginTop: 12 }}>No decision changes vs current policies for the replayed session(s).</p>
      )}
    </>
  )
}

function CopilotTab({
  onDeployed,
}: {
  onDeployed: (policyId: string) => void
}) {
  const queryClient = useQueryClient()
  const generate = useGeneratePolicy()
  const simulate = usePolicySimulation()
  const deploy = useDeployCopilotPolicy()

  const [description, setDescription] = useState('')
  const [policyName, setPolicyName] = useState('copilot-policy')
  const [yamlContent, setYamlContent] = useState('')
  const [sessionId, setSessionId] = useState('demo-finance-session')
  const [approved, setApproved] = useState(false)
  const [validation, setValidation] = useState<{ valid: boolean; error?: string | null } | null>(null)
  const [deployMessage, setDeployMessage] = useState<string | null>(null)

  const canDeploy = Boolean(yamlContent.trim()) && approved && validation?.valid !== false && !deploy.isPending

  function handleGenerate() {
    const trimmed = description.trim()
    if (!trimmed) return
    setDeployMessage(null)
    generate.mutate(
      { description: trimmed, policy_name: policyName.trim() || 'copilot-policy' },
      {
        onSuccess: (data) => {
          setYamlContent(data.yaml_content)
          setValidation({ valid: data.valid, error: data.error })
          setApproved(false)
        },
      },
    )
  }

  function handleSimulate() {
    const yaml = yamlContent.trim()
    if (!yaml) return
    simulate.mutate({
      yaml_content: yaml,
      session_id: sessionId.trim() || null,
    })
  }

  function handleDeploy() {
    const yaml = yamlContent.trim()
    if (!yaml || !approved) return
    setDeployMessage(null)
    deploy.mutate(
      { yaml_content: yaml, approved_by: 'admin' },
      {
        onSuccess: (data) => {
          void queryClient.invalidateQueries({ queryKey: ['policies'] })
          setDeployMessage(data.message)
          setApproved(false)
          onDeployed(data.policy.policy_id)
        },
      },
    )
  }

  return (
    <div className="stack-list" style={{ gap: '1.25rem' }}>
      <Callout>
        Describe a governance rule in plain English. Policy Copilot generates YAML, lets you simulate it against
        historical sessions in the Governance Sandbox, then deploy after human approval.
      </Callout>

      <Panel title="1 · Describe policy" icon={<IconScroll width={18} height={18} />}>
        <div className="stack-list" style={{ gap: '1rem' }}>
          <label className="field">
            <span>Natural language requirement</span>
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Block finance agent from deleting more than 100 records after business hours"
            />
          </label>
          <div className="inline-form">
            <label className="field">
              <span>Policy name</span>
              <input value={policyName} onChange={(e) => setPolicyName(e.target.value)} placeholder="copilot-finance-policy" />
            </label>
            <button type="button" className="btn primary" disabled={!description.trim() || generate.isPending} onClick={handleGenerate}>
              {generate.isPending ? 'Generating…' : 'Generate YAML'}
            </button>
          </div>
          <div>
            <p className="muted small" style={{ margin: '0 0 6px' }}>Try an example:</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {EXAMPLE_PROMPTS.map((example) => (
                <button key={example} type="button" className="btn sm ghost" onClick={() => setDescription(example)}>
                  {example.length > 48 ? `${example.slice(0, 48)}…` : example}
                </button>
              ))}
            </div>
          </div>
        </div>
        {generate.isError ? <ErrorState>Could not generate policy. Check the API is reachable.</ErrorState> : null}
      </Panel>

      <Panel
        title="2 · Review & edit YAML"
        icon={<IconScroll width={18} height={18} />}
        action={
          validation ? (
            <span className={`badge ${validation.valid ? 'status-green' : 'status-red'}`}>
              {validation.valid ? 'Valid YAML' : 'Invalid YAML'}
            </span>
          ) : null
        }
      >
        {!yamlContent ? (
          <EmptyState title="No policy generated yet" hint="Describe a rule above and click Generate YAML." />
        ) : (
          <>
            {validation?.error ? <p className="muted small" style={{ color: 'var(--danger, #dc2626)', marginTop: 0 }}>{validation.error}</p> : null}
            <label className="field">
              <span>Policy YAML (editable)</span>
              <textarea
                className="mono small"
                rows={16}
                value={yamlContent}
                onChange={(e) => {
                  setYamlContent(e.target.value)
                  setValidation(null)
                  setApproved(false)
                }}
                spellCheck={false}
              />
            </label>
          </>
        )}
      </Panel>

      <Panel title="3 · Governance Sandbox" icon={<IconFlask width={18} height={18} />}>
        <p className="muted small" style={{ marginTop: 0 }}>
          Replay audit history against the proposed policy. Leave session blank to scan all stored sessions.
        </p>
        <div className="inline-form" style={{ marginTop: 12 }}>
          <label className="field">
            <span>Session ID (optional)</span>
            <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} placeholder="demo-finance-session" />
          </label>
          <button type="button" className="btn" disabled={!yamlContent.trim() || simulate.isPending} onClick={handleSimulate}>
            {simulate.isPending ? 'Simulating…' : 'Run simulation'}
          </button>
        </div>
        {simulate.isError ? <ErrorState>Simulation failed. Ensure YAML is valid.</ErrorState> : null}
        {simulate.data?.simulation ? <SimulationSummary simulation={simulate.data.simulation} /> : null}
      </Panel>

      <Panel title="4 · Deploy (human approval required)" icon={<IconScroll width={18} height={18} />}>
        <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <input
            type="checkbox"
            checked={approved}
            onChange={(e) => setApproved(e.target.checked)}
            disabled={!yamlContent.trim()}
          />
          <span>I have reviewed this policy and approve deployment to the runtime policy store.</span>
        </label>
        <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button type="button" className="btn primary" disabled={!canDeploy} onClick={handleDeploy}>
            {deploy.isPending ? 'Deploying…' : 'Deploy policy'}
          </button>
          {deploy.isError ? <span className="muted small" style={{ color: 'var(--danger, #dc2626)' }}>Deploy failed — check YAML validity.</span> : null}
          {deployMessage ? <span className="badge status-green">{deployMessage}</span> : null}
        </div>
      </Panel>
    </div>
  )
}

export function PoliciesPage() {
  const policies = usePolicies()
  const [tab, setTab] = useState<TabId>('browse')
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null)

  const policyList = policies.data?.policies ?? []
  const totalRules = policyList.reduce((sum, p) => sum + p.rules.length, 0)

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={<><IconScroll width={13} height={13} /> PS-10.2 · Dynamic Policy Engine</>}
        title="Policy Engine"
        subtitle="Browse deployed governance rules or use Policy Copilot to generate YAML, simulate against audit history, and deploy after human approval."
      />

      <div className="kpi-grid">
        <Kpi label="Deployed policies" value={policyList.length} icon={<IconScroll width={16} height={16} />} />
        <Kpi label="Total rules" value={totalRules} />
        <Kpi label="With inheritance" value={policyList.filter((p) => p.inherits).length} hint="Multi-level chains supported" />
      </div>

      <Tabs<TabId>
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'browse', label: 'Browse policies' },
          { id: 'copilot', label: 'Policy Copilot' },
        ]}
      />

      {tab === 'browse' ? (
        <BrowseTab selectedPolicyId={selectedPolicyId} onSelectPolicy={setSelectedPolicyId} />
      ) : (
        <CopilotTab
          onDeployed={(policyId) => {
            setSelectedPolicyId(policyId)
            setTab('browse')
          }}
        />
      )}
    </section>
  )
}
