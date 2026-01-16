const chatWindow = document.getElementById('chat-window');
const inputEl = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const loadingEl = document.getElementById('loading');
const backendUrl = window.CHAT_BACKEND_URL || '/chat';                 

const cache = new Map();
let lastSentAt = 0;
const MIN_DELAY_MS = 5000;
const TIMEOUT_MS = 30000;

// Load history on startup
window.addEventListener('DOMContentLoaded', loadHistory);

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function sanitizeUrl(url) {
  try {
    const u = new URL(url);
    return (u.protocol === 'http:' || u.protocol === 'https:') ? u.toString() : '#';
  } catch {
    return '#';
  }
}

function renderAssistant(text) {
  let original = text || '';
  original = original.replace(/<think>[\s\S]*?<\/think>/gi, '');
  original = original.replace(/Thinking Process:[\s\S]*?(?=\n\n|$)/gi, '');

  const codeBlocks = [];
  let withoutBlocks = original.replace(/```([\s\S]*?)```/g, (_, code) => {
    const escaped = escapeHtml(code);
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`;
    codeBlocks.push(`<pre><code>${escaped}</code></pre>`);
    return token;
  });

  let t = escapeHtml(withoutBlocks);

  t = t.replace(/`([^`]+?)`/g, (_, c) => `<code>${c}</code>`);

  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => {
    const safe = sanitizeUrl(url);
    return `<a href="${safe}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });

  t = t.replace(/(https?:\/\/[^\s<]+)/g, (m) => {
    const safe = sanitizeUrl(m);
    return `<a href="${safe}" target="_blank" rel="noopener noreferrer">${m}</a>`;
  });

  t = t.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em>$1</em>');
  t = t.replace(/__([^_]+?)__/g, '<strong>$1</strong>');
  t = t.replace(/_(?!_)([^_]+?)_(?!_)/g, '<em>$1</em>');
  t = t.replace(/~~([^~]+?)~~/g, '<del>$1</del>');

  t = t.replace(/^######\s+(.*)$/gm, '<h6>$1</h6>');
  t = t.replace(/^#####\s+(.*)$/gm, '<h5>$1</h5>');
  t = t.replace(/^####\s+(.*)$/gm, '<h4>$1</h4>');
  t = t.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>');
  t = t.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>');
  t = t.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>');

  const lines = t.split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    if (/^\s*-\s+/.test(lines[i])) {
      const items = [];
      while (i < lines.length && /^\s*-\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*-\s+/, ''));
        i++;
      }
      out.push('<ul>' + items.map(li => `<li>${li}</li>`).join('') + '</ul>');
      continue;
    }
    if (/^\s*\d+\.\s+/.test(lines[i])) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      out.push('<ol>' + items.map(li => `<li>${li}</li>`).join('') + '</ol>');
      continue;
    }
    out.push(lines[i]);
    i++;
  }
  t = out.join('\n');

  codeBlocks.forEach((html, idx) => {
    t = t.replace(new RegExp(`@@CODE_BLOCK_${idx}@@`, 'g'), html);
  });

  return t.trim();
}

function normalize(text) {
  return text.trim().toLowerCase();
}

function loadHistory() {
  const history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
  history.forEach(msg => {
    appendMessage(msg.role, msg.text, false);
  });
}

function saveToHistory(role, text) {
  const history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
  history.push({ role, text });
  localStorage.setItem('chatHistory', JSON.stringify(history));
}

function clearHistory() {
  localStorage.removeItem('chatHistory');
  chatWindow.innerHTML = '';
}

function appendMessage(role, text, save = true) {
  const wrapper = document.createElement('div');
  wrapper.className = role === 'user' ? 'msg msg-user' : 'msg msg-assistant';
  if (role === 'assistant') {
    wrapper.innerHTML = renderAssistant(text);
  } else {
    wrapper.textContent = text;
  }
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  if (save) {
    saveToHistory(role, text);
  }
}

function setLoading(loading) {
  loadingEl.classList.toggle('d-none', !loading);
}

function canSend() {
  const now = Date.now();
  return now - lastSentAt >= MIN_DELAY_MS;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  if (!canSend()) {
    const waitMs = MIN_DELAY_MS - (Date.now() - lastSentAt);
    const msg = `Please wait ${(Math.ceil(waitMs / 1000))}s before sending another message.`;
    appendMessage('assistant', msg, false); // Don't save warning
    return;
  }

  appendMessage('user', text);

  const key = normalize(text);
  if (cache.has(key)) {
    appendMessage('assistant', cache.get(key));
    inputEl.value = '';
    return;
  }

  sendBtn.disabled = true;
  setLoading(true);
  lastSentAt = Date.now();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const resp = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!resp.ok) {
      appendMessage('assistant', 'Sorry, I couldn’t reply. Please try again.');
    } else {
      const data = await resp.json();
      let reply = data.reply || data.error || 'No response';
      reply = reply.replace(/<think>[\s\S]*?<\/think>/gi, '');
      reply = reply.replace(/Thinking Process:[\s\S]*?(?=\n\n|$)/gi, '');
      reply = reply.trim();
      appendMessage('assistant', reply);
      cache.set(key, reply);
    }
  } catch (err) {
    appendMessage('assistant', 'Sorry, I couldn’t reply. Please try again.');
  } finally {
    setLoading(false);
    inputEl.value = '';
    setTimeout(() => { sendBtn.disabled = false; }, MIN_DELAY_MS);
  }
}

sendBtn.addEventListener('click', sendMessage);
if (clearBtn) {
  clearBtn.addEventListener('click', clearHistory);
}
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});
