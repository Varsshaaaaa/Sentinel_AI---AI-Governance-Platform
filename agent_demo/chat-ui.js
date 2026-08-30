/**
 * Governed agent chat — user message → Cerebras routes agent → tool intercept → reply
 */

const els = {
  exampleChips: document.getElementById('exampleChips'),
  denyChips: document.getElementById('denyChips'),
  hitlChips: document.getElementById('hitlChips'),
  sessionId: document.getElementById('sessionId'),
  newSessionBtn: document.getElementById('newSessionBtn'),
  chatMessages: document.getElementById('chatMessages'),
  chatForm: document.getElementById('chatForm'),
  chatInput: document.getElementById('chatInput'),
  sendBtn: document.getElementById('sendBtn'),
  apiBadge: document.getElementById('apiBadge'),
  llmBadge: document.getElementById('llmBadge'),
  statusBar: document.getElementById('statusBar'),
  traceEmpty: document.getElementById('traceEmpty'),
  traceContent: document.getElementById('traceContent'),
  traceRoute: document.getElementById('traceRoute'),
  traceIntent: document.getElementById('traceIntent'),
  traceRequest: document.getElementById('traceRequest'),
  traceResponse: document.getElementById('traceResponse'),
  traceDisposition: document.getElementById('traceDisposition'),
};

let sessionId = `chat-${crypto.randomUUID().slice(0, 10)}`;
let history = [];
let activeAgent = null;
let busy = false;

function setStatus(msg) {
  els.statusBar.textContent = msg;
}

function formatJson(obj) {
  return JSON.stringify(obj, null, 2);
}

function dispositionClass(disp) {
  if (disp === 'allow' || disp === 'warn' || disp === 'audit_only') return 'allow';
  if (disp === 'require_hitl') return 'hitl';
  if (disp === 'block' || disp === 'deny') return 'block';
  return '';
}

function appendMessage(role, content, meta = '') {
  const li = document.createElement('li');
  li.className = `chat-msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = content;
  li.appendChild(bubble);
  if (meta) {
    const m = document.createElement('div');
    m.className = 'msg-meta';
    m.textContent = meta;
    li.appendChild(m);
  }
  els.chatMessages.appendChild(li);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function renderExamples(suggestions) {
  els.exampleChips.innerHTML = '';
  (suggestions.try_asking || []).forEach((text) => {
    els.exampleChips.appendChild(makeChip(text, 'chip'));
  });

  els.denyChips.innerHTML = '';
  (suggestions.deny_block || []).forEach((item) => {
    const btn = makeChip(item.text, 'chip chip-deny');
    btn.title = `Expected: ${item.expected} — ${item.reason || ''}`;
    els.denyChips.appendChild(btn);
  });

  els.hitlChips.innerHTML = '';
  (suggestions.hitl || []).forEach((item) => {
    const btn = makeChip(item.text, 'chip chip-hitl');
    btn.title = `Expected: ${item.expected} — ${item.reason || ''}`;
    els.hitlChips.appendChild(btn);
  });
}

function makeChip(text, className) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = className;
  btn.textContent = text;
  btn.addEventListener('click', () => {
    els.chatInput.value = text;
    els.chatInput.focus();
  });
  return btn;
}

function newSession() {
  sessionId = `chat-${crypto.randomUUID().slice(0, 10)}`;
  history = [];
  activeAgent = null;
  els.sessionId.textContent = sessionId;
  els.chatMessages.innerHTML = '';
  els.traceEmpty.hidden = false;
  els.traceContent.hidden = true;
  appendMessage(
    'system',
    'New session. Cerebras will pick the right agent; each tool call is intercepted by SentinelAI.',
  );
  setStatus('New session started');
}

function renderTrace(events) {
  const route = events.find((e) => e.kind === 'route');
  const intent = events.find((e) => e.kind === 'tool_intent');
  const gov = events.find((e) => e.kind === 'governance');

  if (!route && !intent && !gov) {
    els.traceEmpty.hidden = false;
    els.traceContent.hidden = true;
    return;
  }

  els.traceEmpty.hidden = true;
  els.traceContent.hidden = false;

  if (route) {
    els.traceRoute.innerHTML = `
      <strong>Agent routing</strong>
      <span class="mono">${route.agent_name}</span>
      <span class="pill">${route.reason || 'routed'}</span>`;
    els.traceRoute.hidden = false;
  } else {
    els.traceRoute.hidden = true;
  }

  if (intent) {
    els.traceIntent.innerHTML = `
      <strong>Tool call</strong>
      <span class="mono">${intent.tool_name}(${formatJson(intent.params).replace(/\n/g, ' ')})</span>
      <span class="pill ${dispositionClass(gov?.disposition)}">${gov?.disposition || 'pending'}</span>`;
    els.traceIntent.hidden = false;
  } else {
    els.traceIntent.hidden = true;
  }

  if (gov) {
    els.traceRequest.textContent = formatJson(gov.request || {});
    els.traceResponse.textContent = formatJson(gov.response || {});
    els.traceDisposition.textContent = gov.disposition || '';
    els.traceDisposition.className = dispositionClass(gov.disposition);
  }
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || busy) return;

  busy = true;
  els.sendBtn.disabled = true;
  appendMessage('user', message);
  setStatus('Cerebras is routing and planning…');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        history,
        active_agent: activeAgent,
      }),
    });

    const data = await res.json();

    if (!data.ok) {
      appendMessage('error', data.error || 'Chat request failed');
      setStatus(data.error || 'Error');
      return;
    }

    sessionId = data.session_id || sessionId;
    activeAgent = data.agent_name || activeAgent;
    els.sessionId.textContent = sessionId;
    history = data.history || history;

    appendMessage('assistant', data.reply);
    renderTrace(data.events || []);

    const route = (data.events || []).find((e) => e.kind === 'route');
    const gov = (data.events || []).find((e) => e.kind === 'governance');
    if (gov) {
      setStatus(`Routed → ${data.agent_name} · ${gov.disposition}: ${gov.reason || 'ok'}`);
    } else if (route) {
      setStatus(`Routed to ${route.agent_name} — ${route.reason || 'no tool call'}`);
    } else {
      setStatus('Reply ready');
    }
  } catch (err) {
    appendMessage('error', String(err.message || err));
    setStatus('Network error');
  } finally {
    busy = false;
    els.sendBtn.disabled = false;
    els.chatInput.value = '';
    els.chatInput.focus();
  }
}

async function init() {
  try {
    const [ping, llm, suggestionsRes] = await Promise.all([
      fetch('/api/ping').then((r) => r.json()),
      fetch('/api/llm-status').then((r) => r.json()),
      fetch('/api/chat-suggestions').then((r) => r.json()),
    ]);

    els.apiBadge.textContent = ping.ok ? `API · ${ping.agent_count} agents` : 'API offline';
    els.apiBadge.className = `badge ${ping.ok ? 'ok' : 'bad'}`;

    els.llmBadge.textContent = llm.configured ? `LLM · ${llm.model || 'Cerebras'}` : 'LLM not configured';
    els.llmBadge.className = `badge ${llm.configured ? 'ok' : 'bad'}`;

    renderExamples(suggestionsRes);
    newSession();
    setStatus('Ready — try allow, block/deny, or HITL examples');
  } catch (err) {
    setStatus(`Init failed: ${err.message}`);
    els.apiBadge.textContent = 'Init error';
    els.apiBadge.className = 'badge bad';
  }
}

els.chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  sendMessage(els.chatInput.value);
});

els.chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(els.chatInput.value);
  }
});

els.newSessionBtn.addEventListener('click', newSession);

init();
