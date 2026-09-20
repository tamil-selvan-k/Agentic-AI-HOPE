// Campus Event Platform JavaScript
document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const htmlEl = document.documentElement;
  const themeToggleBtn = document.getElementById('theme-toggle');
  const tabBtns = document.querySelectorAll('.tab-btn');
  const viewSections = document.querySelectorAll('.view-section');
  const studentSelect = document.getElementById('student-select');
  const currentStudentLabel = document.getElementById('current-student-label');
  const eventsGrid = document.getElementById('events-grid');
  const eventSearchInput = document.getElementById('event-search');
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');

  let eventsData = [];

  // 1. Theme Toggle (Default: light)
  const savedTheme = localStorage.getItem('theme') || 'light';
  setTheme(savedTheme);

  themeToggleBtn.addEventListener('click', () => {
    const currentTheme = htmlEl.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
  });

  function setTheme(theme) {
    htmlEl.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    themeToggleBtn.textContent = theme === 'dark' ? '☀️' : '🌙';
  }

  // 2. Tab Navigation
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      viewSections.forEach(s => s.classList.remove('active'));

      btn.classList.add('active');
      const targetView = btn.getAttribute('data-view');
      document.getElementById(targetView).classList.add('active');
    });
  });

  // 3. Student Selector
  studentSelect.addEventListener('change', () => {
    currentStudentLabel.textContent = `Student: ${studentSelect.value}`;
  });

  // 4. Fetch & Render Events
  async function fetchEvents() {
    try {
      const res = await fetch('/api/events');
      if (!res.ok) throw new Error('Failed to fetch events');
      eventsData = await res.json();
      renderEvents(eventsData);
    } catch (err) {
      eventsGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-secondary);">Unable to load events. (${err.message})</div>`;
    }
  }

  function renderEvents(events) {
    if (!events.length) {
      eventsGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-secondary);">No events match your search query.</div>`;
      return;
    }

    eventsGrid.innerHTML = events.map(event => {
      const isAvailable = event.seats_available > 0;
      const seatsClass = isAvailable ? 'available' : 'full';
      const seatsText = isAvailable ? `${event.seats_available} seats left` : 'Seats Full';

      return `
        <div class="event-card">
          <span class="card-badge">${escapeHtml(event.category)}</span>
          <h3 class="card-title">${escapeHtml(event.title)}</h3>
          <p class="card-organizer">Organized by ${escapeHtml(event.organizer)}</p>
          <div class="card-meta">
            <span class="seats-badge ${seatsClass}">${seatsText}</span>
            <button class="card-action-btn" onclick="quickRegister(${event.id}, '${escapeHtml(event.title)}')">
              ${isAvailable ? 'Register' : 'View Details'}
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  eventSearchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    const filtered = eventsData.filter(ev =>
      ev.title.toLowerCase().includes(query) ||
      ev.category.toLowerCase().includes(query) ||
      ev.organizer.toLowerCase().includes(query)
    );
    renderEvents(filtered);
  });

  // Quick register from card -> switch to chat tab
  window.quickRegister = (eventId, eventTitle) => {
    const chatTabBtn = document.querySelector('[data-view="chat-view"]');
    chatTabBtn.click();
    chatInput.value = `Can I register for ${eventTitle}?`;
    chatInput.focus();
  };

  // 5. Chat & Streaming Response
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const messageText = chatInput.value.trim();
    if (!messageText) return;

    const studentId = studentSelect.value;
    chatInput.value = '';
    sendBtn.disabled = true;

    // Append User Message
    appendMessage('user', messageText);

    // Append Assistant Message with Streaming Terminal Container
    const assistantMsgEl = document.createElement('div');
    assistantMsgEl.className = 'message assistant';

    const bubbleEl = document.createElement('div');
    bubbleEl.className = 'message-bubble';
    bubbleEl.textContent = 'Processing request with multi-agent queue...';

    const terminalEl = document.createElement('div');
    terminalEl.className = 'terminal-stream';
    terminalEl.textContent = `[system] Enqueued job for student ${studentId}...\n`;

    assistantMsgEl.appendChild(bubbleEl);
    assistantMsgEl.appendChild(terminalEl);
    chatMessages.appendChild(assistantMsgEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: studentId, message: messageText })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let finalAnswer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.replace('data: ', '').trim();
            if (!jsonStr) continue;

            try {
              const data = JSON.parse(jsonStr);
              if (data.type === 'log') {
                terminalEl.textContent += data.text + '\n';
                terminalEl.scrollTop = terminalEl.scrollHeight;
              } else if (data.type === 'answer') {
                finalAnswer = data.text;
                bubbleEl.textContent = finalAnswer;
              }
            } catch (pErr) {
              // Ignore partial JSON chunks
            }
          }
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      if (finalAnswer) {
        bubbleEl.textContent = finalAnswer;
      } else if (!terminalEl.textContent.includes('succeeded')) {
        bubbleEl.textContent = 'Agent completed run.';
      }

      // Refresh events data in background
      fetchEvents();

    } catch (err) {
      bubbleEl.textContent = `Error: ${err.message}`;
      terminalEl.textContent += `\n[error] ${err.message}`;
    } finally {
      sendBtn.disabled = false;
      chatInput.focus();
    }
  });

  function appendMessage(role, text) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${role}`;

    const bubbleEl = document.createElement('div');
    bubbleEl.className = 'message-bubble';
    bubbleEl.textContent = text;

    msgEl.appendChild(bubbleEl);
    chatMessages.appendChild(msgEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, match => {
      const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
      return map[match];
    });
  }

  // Initial load
  fetchEvents();
});
