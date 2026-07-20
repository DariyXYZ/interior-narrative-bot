const tg = window.Telegram?.WebApp;
const statusNode = document.querySelector("#status");
const userLine = document.querySelector("#user-line");
const apiBaseUrl = (window.APP_CONFIG?.API_URL || "").replace(/\/$/, "");

if (tg) {
  tg.ready();
  tg.expand();
}

const initData = tg?.initData || "";
const telegramUser = tg?.initDataUnsafe?.user;

if (telegramUser) {
  const label = telegramUser.username ? `@${telegramUser.username}` : telegramUser.first_name;
  userLine.textContent = label || "Профиль Telegram";
} else {
  userLine.textContent = "Предпросмотр вне Telegram";
}

async function api(path, options = {}) {
  if (!apiBaseUrl) {
    throw new Error("API_URL не настроен");
  }
  const headers = {
    "X-Telegram-Init-Data": initData,
    "ngrok-skip-browser-warning": "1",
    ...(options.headers || {}),
  };
  if (options.body) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

// ═══════════════════════════════════════════
// SCREENS
// ═══════════════════════════════════════════

const screens = {
  start: document.getElementById("screen-start"),
  project: document.getElementById("screen-project"),
  question: document.getElementById("screen-question"),
  results: document.getElementById("screen-results"),
  history: document.getElementById("screen-history"),
};

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.hidden = key !== name;
  });
  window.scrollTo({ top: 0 });
}

const sessionKey = (testKey) => `interior-narrative:session:${testKey}`;

// ═══════════════════════════════════════════
// STATE — один активный тест за раз
// ═══════════════════════════════════════════

let quiz = null;
// quiz = { testKey, sessionId, content, questions, index, answers: {qid: optId}, pendingProjectDraft }

let busy = false;
let savingAnswer = false;

function setStatus(text) {
  statusNode.textContent = text;
}

// ═══════════════════════════════════════════
// START → выбор теста
// ═══════════════════════════════════════════

async function startTest(testKey) {
  if (!initData) {
    setStatus("Запустите Mini App из Telegram, чтобы начать тест.");
    return;
  }
  if (busy) return;

  if (testKey === "project-narrative") {
    showScreen("project");
    return;
  }

  busy = true;
  setStatus("Загружаем вопросы…");
  try {
    await beginSession(testKey, null);
  } catch (error) {
    setStatus(`Не удалось начать тест: ${error.message}`);
  } finally {
    busy = false;
  }
}

async function beginSession(testKey, projectId) {
  const content = await api(`/api/v1/tests/${testKey}`);

  // Резюмируем незавершённую сессию этого теста, если она есть.
  const savedSessionId = localStorage.getItem(sessionKey(testKey));
  let sessionId = null;
  let answers = {};

  if (savedSessionId) {
    try {
      const existing = await api(`/api/v1/sessions/${savedSessionId}`);
      if (existing.status === "in_progress" && (!projectId || existing.project_id === projectId)) {
        sessionId = existing.id;
        answers = existing.answers || {};
      }
    } catch {
      localStorage.removeItem(sessionKey(testKey));
    }
  }

  if (!sessionId) {
    const session = await api("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ test_key: testKey, project_id: projectId || undefined }),
    });
    sessionId = session.id;
    localStorage.setItem(sessionKey(testKey), sessionId);
  }

  const answeredIds = new Set(Object.keys(answers));
  const firstUnanswered = content.questions.findIndex((q) => !answeredIds.has(q.id));

  quiz = {
    testKey,
    sessionId,
    content,
    answers,
    index: firstUnanswered === -1 ? content.questions.length - 1 : firstUnanswered,
  };

  setStatus("");
  renderQuestion();
  showScreen("question");
}

// ═══════════════════════════════════════════
// ПРОЕКТ (для теста 2)
// ═══════════════════════════════════════════

document.getElementById("project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const form = event.target;
  const codeName = form.code_name.value.trim();
  if (!codeName) {
    document.getElementById("project-status").textContent = "Укажите код проекта.";
    return;
  }
  busy = true;
  document.getElementById("project-status").textContent = "Создаём проект…";
  try {
    const areaRaw = form.area_m2.value.trim();
    const project = await api("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify({
        code_name: codeName,
        object_type: form.object_type.value,
        area_m2: areaRaw ? Number(areaRaw) : undefined,
      }),
    });
    document.getElementById("project-status").textContent = "";
    await beginSession("project-narrative", project.id);
  } catch (error) {
    document.getElementById("project-status").textContent = `Не удалось создать проект: ${error.message}`;
  } finally {
    busy = false;
  }
});

document.getElementById("project-cancel").addEventListener("click", () => {
  showScreen("start");
});

// ═══════════════════════════════════════════
// ЭКРАН ВОПРОСА
// ═══════════════════════════════════════════

function renderQuestion() {
  const { content, index, answers } = quiz;
  const question = content.questions[index];
  const total = content.questions.length;

  document.getElementById("q-counter").textContent = `Вопрос ${index + 1} из ${total}`;
  document.getElementById("q-percent").textContent = `${Math.round((index / total) * 100)}%`;
  document.getElementById("progress-fill").style.width = `${Math.round((index / total) * 100)}%`;
  document.getElementById("q-text").textContent = question.text;
  document.getElementById("save-indicator").textContent = "";

  const list = document.getElementById("options-list");
  list.innerHTML = "";
  question.options.forEach((option) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "option-btn" + (option.id === "dunno" ? " dunno" : "");
    btn.textContent = option.text;
    if (answers[question.id] === option.id) {
      btn.classList.add("chosen");
    }
    btn.addEventListener("click", () => chooseOption(question.id, option.id, btn));
    list.appendChild(btn);
  });

  const backBtn = document.getElementById("btn-back");
  backBtn.style.visibility = index === 0 ? "hidden" : "visible";
}

async function chooseOption(questionId, optionId, buttonEl) {
  if (savingAnswer) return;
  savingAnswer = true;

  document.querySelectorAll(".option-btn").forEach((el) => { el.disabled = true; });
  const indicator = document.getElementById("save-indicator");
  indicator.textContent = "Сохраняем…";

  quiz.answers[questionId] = optionId;
  buttonEl.classList.add("chosen");

  try {
    await api(`/api/v1/sessions/${quiz.sessionId}/answers/${questionId}`, {
      method: "PUT",
      body: JSON.stringify({ option_id: optionId }),
    });
    indicator.textContent = "";
  } catch (error) {
    indicator.textContent = `Не сохранилось: ${error.message}`;
    document.querySelectorAll(".option-btn").forEach((el) => { el.disabled = false; });
    savingAnswer = false;
    return;
  }

  setTimeout(async () => {
    savingAnswer = false;
    if (quiz.index + 1 >= quiz.content.questions.length) {
      await finishQuiz();
    } else {
      quiz.index += 1;
      renderQuestion();
    }
  }, 160);
}

document.getElementById("btn-back").addEventListener("click", () => {
  if (savingAnswer || !quiz || quiz.index === 0) return;
  quiz.index -= 1;
  renderQuestion();
});

async function finishQuiz() {
  setStatus("");
  document.getElementById("q-text").textContent = "Считаем результат…";
  document.getElementById("options-list").innerHTML = "";
  try {
    const result = await api(`/api/v1/sessions/${quiz.sessionId}/complete`, { method: "POST" });
    localStorage.removeItem(sessionKey(quiz.testKey));
    renderResult(result);
    showScreen("results");
  } catch (error) {
    document.getElementById("q-text").textContent = `Не удалось получить результат: ${error.message}`;
  }
}

// ═══════════════════════════════════════════
// ЭКРАН РЕЗУЛЬТАТА
// ═══════════════════════════════════════════

async function loadFullResult(sessionId) {
  return api(`/api/v1/sessions/${sessionId}/result`);
}

function renderResult(resultSummary) {
  loadFullResult(resultSummary.session_id || resultSummary.id)
    .then(renderResultDetail)
    .catch(() => renderResultDetail(resultSummary));
}

function renderResultDetail(result) {
  const primary = result.primary_detail || {};
  document.getElementById("result-kicker").textContent =
    result.test_key === "designer-profile" ? "Ваш ведущий архетип" : "Рабочая гипотеза нарратива";
  document.getElementById("result-name").textContent = primary.name || result.primary_narrative_key;
  document.getElementById("result-subtitle").textContent = primary.subtitle || "";
  document.getElementById("fit-bar").style.width = `${result.primary_score}%`;
  document.getElementById("fit-percent").textContent = `${result.primary_score}%`;
  document.getElementById("confidence-line").textContent = `Уверенность результата: ${result.confidence}%`;
  document.getElementById("result-text").textContent = result.result_text;

  const detail = document.getElementById("result-detail");
  detail.innerHTML = "";
  if (primary.desc) {
    detail.appendChild(makeDetailBlock("Подробнее", primary.desc));
  }
  if (primary.strengths?.length) {
    const wrap = document.createElement("div");
    const h = document.createElement("h3");
    h.textContent = "Сильные стороны";
    wrap.appendChild(h);
    primary.strengths.forEach((s) => {
      const tag = document.createElement("span");
      tag.className = "strength-tag";
      tag.textContent = s;
      wrap.appendChild(tag);
    });
    detail.appendChild(wrap);
  }
  if (primary.blindspot) detail.appendChild(makeDetailBlock("Слепая зона", primary.blindspot));
  if (primary.thesis) detail.appendChild(makeDetailBlock("Тезис", primary.thesis));
  if (primary.client_argument) detail.appendChild(makeDetailBlock("Аргумент для заказчика", primary.client_argument));
  if (primary.visual_direction) detail.appendChild(makeDetailBlock("Визуальный язык", primary.visual_direction));
  if (primary.risks) detail.appendChild(makeDetailBlock("Риски", primary.risks));
  if (primary.next_step) detail.appendChild(makeDetailBlock("Следующий шаг", primary.next_step));
  if (primary.advice) detail.appendChild(makeDetailBlock("Попробуйте в следующем проекте", primary.advice));

  const altWrap = document.getElementById("alternatives");
  altWrap.innerHTML = "";
  (result.alternatives || []).forEach((alt) => {
    const card = document.createElement("div");
    card.className = "alt-card";
    card.innerHTML = `<strong>${alt.name}</strong><span>${alt.fit_percent}%</span>`;
    altWrap.appendChild(card);
  });
}

function makeDetailBlock(title, text) {
  const wrap = document.createElement("div");
  const h = document.createElement("h3");
  h.textContent = title;
  const p = document.createElement("p");
  p.textContent = text;
  wrap.appendChild(h);
  wrap.appendChild(p);
  return wrap;
}

document.getElementById("btn-restart").addEventListener("click", () => {
  quiz = null;
  setStatus("");
  showScreen("start");
});

// ═══════════════════════════════════════════
// ИСТОРИЯ
// ═══════════════════════════════════════════

const TEST_LABELS = {
  "designer-profile": "Какой вы тип дизайнера",
  "project-narrative": "Нарратив для проекта",
};

async function showHistory() {
  if (!initData) {
    setStatus("История доступна при запуске из Telegram.");
    return;
  }
  if (busy) return;
  busy = true;
  showScreen("history");
  const list = document.getElementById("history-list");
  list.innerHTML = "<p class=\"status\">Загружаем…</p>";
  try {
    const results = await api("/api/v1/results");
    if (!results.length) {
      list.innerHTML = "<p class=\"status\">Сохранённых результатов пока нет.</p>";
    } else {
      list.innerHTML = "";
      results.forEach((r) => {
        const item = document.createElement("div");
        item.className = "history-item";
        const date = r.completed_at ? new Date(r.completed_at).toLocaleDateString("ru-RU") : "";
        item.innerHTML = `
          <div class="h-top"><span>${TEST_LABELS[r.test_key] || r.test_key}</span><span>${date}</span></div>
          <strong>${r.primary_narrative_key} · ${r.primary_score}%</strong>
        `;
        list.appendChild(item);
      });
    }
  } catch (error) {
    list.innerHTML = `<p class="status">Не удалось загрузить историю: ${error.message}</p>`;
  } finally {
    busy = false;
  }
}

document.getElementById("history-back").addEventListener("click", () => showScreen("start"));

document.querySelectorAll("[data-test]").forEach((button) => {
  button.addEventListener("click", () => startTest(button.dataset.test));
});

document.querySelector("#history-button").addEventListener("click", showHistory);

if (new URLSearchParams(window.location.search).get("screen") === "results") {
  showHistory();
}
