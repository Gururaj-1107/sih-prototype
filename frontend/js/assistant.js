/**
 * CashOut Forecast — Investigator Intelligence Assistant
 * Evidence-grounded conversational analyst answering queries from structured database content.
 */

async function sendAssistantMessage(event) {
  if (event) event.preventDefault();
  const inputElem = document.getElementById('assistantInput');
  const query = inputElem.value.trim();
  if (!query) return;

  inputElem.value = '';
  await executeAssistantQuery(query);
}

function askAssistantPrompt(promptText) {
  const inputElem = document.getElementById('assistantInput');
  if (inputElem) inputElem.value = promptText;
  executeAssistantQuery(promptText);
}

async function executeAssistantQuery(question) {
  const chatWindow = document.getElementById('assistantChatWindow');
  const btn = document.getElementById('btnSendAssistant');

  // 1. Append User Message
  appendChatMessage('user', question);

  // 2. Append Loading Placeholder
  const loadingId = 'msg-loading-' + Date.now();
  const loadingElem = document.createElement('div');
  loadingElem.id = loadingId;
  loadingElem.className = 'chat-message bot-message';
  loadingElem.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-bubble text-muted italic">Consulting intelligence records & SHAP evidence...</div>
  `;
  chatWindow.appendChild(loadingElem);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  if (btn) btn.disabled = true;

  try {
    const payload = {
      question: question,
      prediction_id: window.currentCaseId || null
    };

    const resp = await authFetch('/assistant/query', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    const data = await resp.json();
    loadingElem.remove();

    // 3. Render Formatted Bot Message
    appendChatMessage('bot', data.answer, data);
  } catch (err) {
    loadingElem.remove();
    appendChatMessage('bot', 'Error querying assistant engine. Please ensure the backend API is reachable.');
  } finally {
    if (btn) btn.disabled = false;
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }
}

function appendChatMessage(sender, text, data = {}) {
  const chatWindow = document.getElementById('assistantChatWindow');
  if (!chatWindow) return;

  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-message ${sender === 'user' ? 'user-message' : 'bot-message'}`;

  // Simple Markdown parsing for bullet points and bold text
  let formattedHtml = text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/_(.*?)_/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/• (.*?)(?=(<br\/>|• |$))/g, '<div class="bullet-item">• $1</div>');

  if (sender === 'user') {
    msgDiv.innerHTML = `
      <div class="msg-bubble">${escapeHtml(text)}</div>
      <div class="msg-avatar user-avatar-icon">OF</div>
    `;
  } else {
    msgDiv.innerHTML = `
      <div class="msg-avatar">AI</div>
      <div class="msg-bubble">${formattedHtml}</div>
    `;
    
    const bubble = msgDiv.querySelector('.msg-bubble');
    // Render context entities
    if (data.context_entities && data.context_entities.length > 0) {
      const entityHtml = data.context_entities.map(e => 
        `<span class="context-badge">${e.type}: ${e.id}</span>`
      ).join(' ');
      bubble.innerHTML += `<div style="margin-top:8px;">${entityHtml}</div>`;
    }

    // Render suggested actions
    if (data.suggested_actions && data.suggested_actions.length > 0) {
      const actionsHtml = data.suggested_actions.map(a => 
        `<button class="action-chip" onclick="handleAssistantAction('${a.action}', ${JSON.stringify(a.params).replace(/"/g, '&quot;')})">${a.label}</button>`
      ).join('');
      bubble.innerHTML += `<div class="action-chips-bar">${actionsHtml}</div>`;
    }
  }

  chatWindow.appendChild(msgDiv);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function escapeHtml(string) {
  const entityMap = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  };
  return String(string).replace(/[&<>"']/g, s => entityMap[s]);
}

function handleAssistantAction(action, params) {
  if (action === 'view_case') switchView('view-workbench');
  else if (action === 'view_map') switchView('view-map');
  else if (action === 'export_pdf') exportEvidencePDF();
  else if (action === 'view_decoys') switchView('view-decoys');
  else if (action === 'run_demo') triggerDemoScenario();
}

window.askAssistantPrompt = askAssistantPrompt;
window.sendAssistantMessage = sendAssistantMessage;
