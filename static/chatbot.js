const chatWindow = document.getElementById('chat-window');
const inputEl = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const loadingEl = document.getElementById('loading');
const backendUrl = window.CHAT_BACKEND_URL || '/chat';

const cache = new Map();
let lastSentAt = 0;
const MIN_DELAY_MS = 5000;
const TIMEOUT_MS = 30000;

function normalize(text) {
  return text.trim().toLowerCase();
}

function appendMessage(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = role === 'user' ? 'msg msg-user' : 'msg msg-assistant';
  wrapper.textContent = text;
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
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
    appendMessage('assistant', `Please wait ${(Math.ceil(waitMs / 1000))}s before sending another message.`);
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
      // Clean up response if backend didn't catch it
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
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});
