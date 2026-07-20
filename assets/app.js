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
  return response.json();
}

let busy = false;

async function startTest(testKey) {
  if (!initData) {
    statusNode.textContent = "Запустите Mini App из Telegram, чтобы начать тест.";
    return;
  }
  if (busy) {
    return;
  }
  busy = true;
  statusNode.textContent = "Создаём прохождение…";
  try {
    const session = await api("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ test_key: testKey }),
    });
    statusNode.textContent = `Сессия ${session.id.slice(0, 8)} создана. Экран вопросов — следующий этап разработки.`;
  } catch (error) {
    statusNode.textContent = `Не удалось начать тест: ${error.message}`;
  } finally {
    busy = false;
  }
}

async function showHistory() {
  if (!initData) {
    statusNode.textContent = "История доступна при запуске из Telegram.";
    return;
  }
  if (busy) {
    return;
  }
  busy = true;
  try {
    const results = await api("/api/v1/results");
    statusNode.textContent = results.length ? `Сохранённых результатов: ${results.length}` : "Сохранённых результатов пока нет.";
  } catch (error) {
    statusNode.textContent = `Не удалось загрузить историю: ${error.message}`;
  } finally {
    busy = false;
  }
}

document.querySelectorAll("[data-test]").forEach((button) => {
  button.addEventListener("click", () => startTest(button.dataset.test));
});

document.querySelector("#history-button").addEventListener("click", showHistory);

if (new URLSearchParams(window.location.search).get("screen") === "results") {
  showHistory();
}
