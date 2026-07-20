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

// Висячие предлоги/короткие слова — неразрывный пробел (U+00A0), не обычный.
// Порт 1:1 из шипнутого теста (index.html noWidow), включая lookbehind и тире.
function noWidow(str) {
  if (!str) return "";
  return str
    .replace(/(?<!\S)(\S{1,3})\s/g, "$1 ")
    .replace(/\s—/g, " —");
}

function setNoWidowText(el, text) {
  el.innerHTML = "";
  el.appendChild(document.createTextNode(noWidow(text)));
}

const DESIGNER_ARCHETYPE_IMAGE = (key) => `./assets/archetypes/${key}.jpg`;

function renderResultDetail(result) {
  const isDesignerProfile = result.test_key === "designer-profile";
  const primary = result.primary_detail || {};
  const ranking = result.full_ranking || [];

  document.getElementById("result-kicker").textContent = isDesignerProfile
    ? "Ваш ведущий архетип"
    : "Рабочая гипотеза нарратива";
  document.getElementById("result-name").textContent = primary.name || result.primary_narrative_key;
  document.getElementById("result-subtitle").textContent = primary.subtitle || "";
  document.getElementById("result-card").style.setProperty("--arch-color", primary.color || "#2563EB");

  const imageWrap = document.getElementById("result-image-wrap");
  if (isDesignerProfile) {
    document.getElementById("result-image").src = DESIGNER_ARCHETYPE_IMAGE(result.primary_narrative_key);
    document.getElementById("result-image").alt = primary.name || "";
    imageWrap.hidden = false;
  } else {
    imageWrap.hidden = true;
  }

  document.getElementById("fit-bar").style.width = `${result.primary_score}%`;
  document.getElementById("fit-bar").style.background = primary.color || "#2563EB";
  document.getElementById("fit-percent").textContent = `${result.primary_score}%`;
  document.getElementById("confidence-line").textContent = `Уверенность результата: ${result.confidence}%`;
  setNoWidowText(document.getElementById("result-text"), result.result_text);

  const detail = document.getElementById("result-detail");
  detail.innerHTML = "";
  if (primary.desc) detail.appendChild(makeDetailBlock("Подробнее", primary.desc));
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
  if (primary.blindspot) {
    const box = document.createElement("div");
    box.className = "blindspot-block";
    const strong = document.createElement("strong");
    strong.textContent = "Слепая зона: ";
    box.appendChild(strong);
    box.appendChild(document.createTextNode(noWidow(primary.blindspot)));
    detail.appendChild(box);
  }
  if (primary.thesis) detail.appendChild(makeDetailBlock("Тезис", primary.thesis));
  if (primary.client_argument) detail.appendChild(makeDetailBlock("Аргумент для заказчика", primary.client_argument));
  if (primary.visual_direction) detail.appendChild(makeDetailBlock("Визуальный язык", primary.visual_direction));
  if (primary.risks) detail.appendChild(makeDetailBlock("Риски", primary.risks));
  if (primary.next_step) detail.appendChild(makeDetailBlock("Следующий шаг", primary.next_step));
  if (primary.advice) detail.appendChild(makeDetailBlock("Попробуйте в следующем проекте", primary.advice));

  document.getElementById("wheel-title").textContent = isDesignerProfile
    ? "Профиль дизайнерского мышления"
    : "Профиль проектных стратегий";

  renderWheel(ranking);
  renderSummary(ranking, isDesignerProfile);
  renderRankedList(ranking, isDesignerProfile);
}

function makeDetailBlock(title, text) {
  const wrap = document.createElement("div");
  const h = document.createElement("h3");
  h.textContent = title;
  const p = document.createElement("p");
  p.appendChild(document.createTextNode(noWidow(text)));
  wrap.appendChild(h);
  wrap.appendChild(p);
  return wrap;
}

// ── Колесо: SVG-диаграмма, нормировка от максимального fit% в наборе ──
// (в оригинале — от топ-сырого-скора; здесь колонка данных уже % от
// собственного максимума нарратива, поэтому нормируем от топового %.)
function renderWheel(ranking) {
  const section = document.getElementById("wheel-section");
  if (!ranking.length) { section.hidden = true; return; }
  section.hidden = false;

  const svg = document.getElementById("wheel-svg");
  svg.innerHTML = "";
  const cx = 220, cy = 220, maxR = 155;
  const n = ranking.length;
  const step = (2 * Math.PI) / n;
  const startOffset = -Math.PI / 2;
  const ns = "http://www.w3.org/2000/svg";

  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  }

  [0.25, 0.5, 0.75, 1.0].forEach((r) => {
    svg.appendChild(el("circle", {
      cx, cy, r: maxR * r, fill: "none",
      stroke: r === 1.0 ? "#CBD5E1" : "#E8ECF2",
      "stroke-width": r === 1.0 ? "1.5" : "1",
      "stroke-dasharray": r < 1 ? "3 4" : "none",
    }));
  });

  for (let i = 0; i < n; i++) {
    const angle = startOffset + i * step;
    svg.appendChild(el("line", {
      x1: cx, y1: cy,
      x2: cx + maxR * Math.cos(angle), y2: cy + maxR * Math.sin(angle),
      stroke: "#E8ECF2", "stroke-width": "1",
    }));
  }

  const topPct = Math.max(1, ...ranking.map((r) => r.fit_percent || 0));
  ranking.forEach((item, i) => {
    const pct = item.fit_percent || 0;
    const norm = pct / topPct;
    const r = Math.max(norm * maxR * 0.9, pct > 0 ? 4 : 0);
    const a1 = startOffset + i * step;
    const a2 = startOffset + (i + 1) * step;
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
    svg.appendChild(el("path", {
      d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2} Z`,
      fill: item.color || "#2563EB", "fill-opacity": "0.72",
      stroke: item.color || "#2563EB", "stroke-width": "0.5",
    }));
  });

  svg.appendChild(el("circle", { cx, cy, r: maxR, fill: "none", stroke: "#CBD5E1", "stroke-width": "1.5" }));
  svg.appendChild(el("circle", { cx, cy, r: 4, fill: "#94A3B8" }));

  ranking.forEach((item, i) => {
    const midAngle = startOffset + (i + 0.5) * step;
    const labelR = maxR + 26;
    const lx = cx + labelR * Math.cos(midAngle);
    const ly = cy + labelR * Math.sin(midAngle);
    const text = el("text", {
      x: lx, y: ly, "text-anchor": "middle", "dominant-baseline": "middle",
      "font-size": "9", "font-weight": "500", fill: "#64748B",
      "font-family": "Inter, system-ui, sans-serif",
    });
    text.textContent = item.short_name || item.name;
    svg.appendChild(text);
  });
}

// ── Саммари: топ-3 чипа + текст, совет по нижним-3 (только там, где есть advice) ──
function renderSummary(ranking, isDesignerProfile) {
  const section = document.getElementById("summary-section");
  if (!isDesignerProfile || ranking.length < 6) { section.hidden = true; return; }
  section.hidden = false;

  const top3 = ranking.slice(0, 3);
  const bottom3 = ranking.slice(-3).reverse();

  const chips = top3.map((a) =>
    `<div class="palette-chip"><span class="dot" style="background:${a.color}"></span>${a.name} ${a.fit_percent}%</div>`
  ).join("");

  const blindNames = bottom3.map((a) => a.name).join(", ");
  const adviceItems = bottom3
    .filter((a) => a.advice)
    .map((a) => `<p><strong>${a.name}.</strong> ${noWidow(a.advice)}</p>`)
    .join("");

  section.innerHTML = `
    <h3>Что говорит ваш профиль</h3>
    <div class="summary-palette">${chips}</div>
    <div class="summary-text">
      <p>${noWidow(`Ваш основной подход — ${top3[0].name}. Его хорошо дополняют ${top3[1].name} и ${top3[2].name} — вместе они дают гибкость под разные задачи.`)}</p>
      <p>${noWidow(`В профиле меньше — ${blindNames}. Это просто инструменты, которые пока реже используются в проектах.`)}</p>
    </div>
    ${adviceItems ? `<div class="summary-advice"><strong>Попробуйте в следующем проекте:</strong>${adviceItems}</div>` : ""}
  `;
}

// ── Полный список: все нарративы, раскрывающиеся карточки ──
function renderRankedList(ranking, isDesignerProfile) {
  const title = document.getElementById("ranked-title");
  title.textContent = isDesignerProfile
    ? "Все архетипы — от ближайшего к дальнему"
    : "Все нарративы — от ближайшего к дальнему";

  const list = document.getElementById("ranked-list");
  list.innerHTML = "";
  ranking.forEach((item, idx) => {
    const card = document.createElement("div");
    card.className = "archetype-card";
    card.style.setProperty("--card-color", item.color || "#2563EB");

    const bodyParts = [];
    const bodyText = item.desc || item.thesis;
    if (bodyText) bodyParts.push(`<p>${noWidow(bodyText)}</p>`);
    if (item.when_fits) bodyParts.push(`<p>${noWidow(item.when_fits)}</p>`);
    const tags = item.strengths?.length
      ? `<div class="mini-strengths">${item.strengths.map((s) => `<span class="mini-tag">${s}</span>`).join("")}</div>`
      : "";

    card.innerHTML = `
      <div class="card-header">
        <div class="card-rank">${idx + 1}</div>
        <div class="card-color-dot" style="background:${item.color}"></div>
        <div class="card-name">
          <strong>${item.name}</strong>
          <span>${item.subtitle || ""}</span>
        </div>
        <div class="card-score-area">
          <div class="score-bar-wrap"><div class="score-bar-fill" style="width:${item.fit_percent}%;background:${item.color}"></div></div>
          <div class="score-num">${item.fit_percent}%</div>
        </div>
        <div class="card-chevron"><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      </div>
      <div class="card-body">${bodyParts.join("")}${tags}</div>
    `;
    card.querySelector(".card-header").addEventListener("click", () => card.classList.toggle("expanded"));
    list.appendChild(card);
  });
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
