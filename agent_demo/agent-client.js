/**
 * Browser-side governed agent — calls POST /tool/intercept like a real agent UI.
 * Requests go through /api/governance/* (local proxy); UI shows the production URL.
 */

const PROXY_PREFIX = '/api/governance';

/** @typedef {{ tool_name: string, action_type?: string, params?: object, data_scope_size?: number, classification?: string, timestamp?: string }} ToolStep */

export class GovernedAgentClient {
  /**
   * @param {object} opts
   * @param {string} opts.apiBase - e.g. https://.../v1
   * @param {string} opts.agentId
   * @param {string} opts.agentName
   * @param {function} opts.onEvent
   */
  constructor({ apiBase, agentId, agentName, onEvent }) {
    this.apiBase = apiBase.replace(/\/$/, '');
    this.agentId = agentId;
    this.agentName = agentName;
    this.sessionId = `web-${crypto.randomUUID().slice(0, 10)}`;
    this.onEvent = onEvent || (() => {});
    this.executed = [];
    this.stopped = [];
    this.lastRequest = null;
    this.lastResponse = null;
  }

  interceptUrl() {
    return `${this.apiBase}/tool/intercept`;
  }

  buildPayload(step) {
    const ctx = {
      agent_id: this.agentId,
      session_id: this.sessionId,
      tool_name: step.tool_name,
      action_type: step.action_type || 'read',
      tool_params: step.params || {},
      data_scope_size: step.data_scope_size ?? 0,
      session_data_classification: step.classification || 'internal',
      user_id: 'demo-user',
      framework: 'agent_demo_ui',
    };
    if (step.timestamp) ctx.timestamp = step.timestamp;
    return { context: ctx, shadow_mode: false };
  }

  /**
   * @param {ToolStep} step
   */
  async callTool(step) {
    const payload = this.buildPayload(step);
    const displayUrl = this.interceptUrl();

    this.onEvent({
      kind: 'api_request',
      method: 'POST',
      url: displayUrl,
      body: payload,
    });

    this.lastRequest = { method: 'POST', url: displayUrl, body: payload };

    const res = await fetch(`${PROXY_PREFIX}/tool/intercept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    this.lastResponse = { status: res.status, body: data };

    this.onEvent({
      kind: 'api_response',
      status: res.status,
      url: displayUrl,
      body: data,
    });

    const disp = data.disposition;
    const params = step.params || {};

    this.onEvent({
      kind: 'agent_intent',
      message: `Agent wants ${step.tool_name}(${JSON.stringify(params)})`,
      tool: step.tool_name,
    });

    this.onEvent({
      kind: 'governance',
      disposition: disp,
      message: data.reason || 'no reason',
      tool: step.tool_name,
      ticket_id: data.ticket_id,
    });

    if (disp === 'allow' || disp === 'warn' || disp === 'audit_only') {
      const mockMsg = mockToolResult(step.tool_name, params);
      this.executed.push(step.tool_name);
      this.onEvent({ kind: 'executed', message: mockMsg, tool: step.tool_name });
      return { ok: true, disposition: disp, data };
    }

    if (disp === 'require_hitl') {
      this.stopped.push(step.tool_name);
      this.onEvent({
        kind: 'hitl',
        message: `Waiting for approval — ticket ${data.ticket_id}`,
        tool: step.tool_name,
        ticket_id: data.ticket_id,
      });
      return { ok: false, disposition: disp, data };
    }

    this.stopped.push(step.tool_name);
    this.onEvent({
      kind: 'stopped',
      message: 'Governance stopped this tool — not executed',
      tool: step.tool_name,
      disposition: disp,
    });
    return { ok: false, disposition: disp, data };
  }

  /**
   * @param {ToolStep[]} steps
   * @param {string} expected
   */
  async runSteps(steps, expected) {
    this.executed = [];
    this.stopped = [];
    this.sessionId = `web-${crypto.randomUUID().slice(0, 10)}`;

    let lastDisp = null;
    for (const step of steps) {
      const result = await this.callTool(step);
      lastDisp = result.disposition;
      await sleep(350);
    }

    const passed = lastDisp === expected;
    this.onEvent({
      kind: 'result',
      passed,
      expected,
      actual: lastDisp,
      session_id: this.sessionId,
      replay_url: `${this.apiBase}/decision/replay/${this.sessionId}`,
    });
    return { passed, actual: lastDisp, expected, sessionId: this.sessionId };
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function mockToolResult(toolName, params) {
  const p = params || {};
  const map = {
    db_query: () => `[TOOL] db_query → read from '${p.table || 'table'}'`,
    db_delete: () => `[TOOL] db_delete → deleted ${p.count ?? '?'} rows`,
    identity_verify: () => `[TOOL] identity_verify → verified ${p.customer_id}`,
    payment_process: () => `[TOOL] payment_process → charged ${p.currency || 'USD'} ${p.amount}`,
    email_send: () => `[TOOL] email_send → sent to ${p.to}`,
    crm_read: () => `[TOOL] crm_read → fetched CRM data`,
    hr_records: () => `[TOOL] hr_records → read employee ${p.employee_id}`,
    api_call: () => `[TOOL] api_call → ${p.url}`,
  };
  return (map[toolName] || (() => `[TOOL] ${toolName} → mock ok`))();
}

/** @param {string} apiBase */
export async function fetchAgents(apiBase) {
  const res = await fetch(`${PROXY_PREFIX}/agents`);
  if (!res.ok) throw new Error(`GET /agents failed: ${res.status}`);
  const data = await res.json();
  return data.agents || [];
}

export async function loadScenarios() {
  const res = await fetch('/api/scenarios');
  if (!res.ok) throw new Error('Failed to load scenarios');
  return res.json();
}

export async function pingApi() {
  const res = await fetch('/api/ping');
  return res.json();
}

export function formatJson(obj) {
  return JSON.stringify(obj, null, 2);
}
