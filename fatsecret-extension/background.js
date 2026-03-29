const PROXY_URL = "http://127.0.0.1:5001/fatsecret/update";
const API_KEY   = "myhealthkey2026";
const DIARY_URL = "https://foods.fatsecret.com/Diary.aspx?pa=fj";

// Schedule daily sync at 21:25
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("fatsecret-daily", {
    when: nextAlarmAt(21, 25),
    periodInMinutes: 24 * 60
  });
  console.log("FatSecret Daily Sync: alarm scheduled at 21:25");
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "fatsecret-daily") {
    syncDiary();
  }
});

function nextAlarmAt(hour, minute) {
  const now = new Date();
  const target = new Date();
  target.setHours(hour, minute, 0, 0);
  if (target <= now) target.setDate(target.getDate() + 1);
  return target.getTime();
}

async function syncDiary() {
  try {
    const resp = await fetch(DIARY_URL, { credentials: "include" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const html = await resp.text();

    if (html.includes("Auth.aspx") || html.includes("Sign in to FatSecret")) {
      throw new Error("Not logged in to FatSecret");
    }

    const data = parseDiary(html);
    await postToProxy(data);

    chrome.storage.local.set({
      lastSync: new Date().toISOString(),
      lastData: data,
      lastError: null
    });
    console.log("FatSecret synced:", data.total);
  } catch (err) {
    chrome.storage.local.set({ lastError: err.message, lastSync: new Date().toISOString() });
    console.error("FatSecret sync failed:", err.message);
  }
}

function parseDiary(html) {
  // Strip HTML tags
  const text = html.replace(/<[^>]+>/g, " ").replace(/[ \t]+/g, " ");

  // Total: Fat Carbs Prot Cals header then numbers
  let total = null;
  const tm = text.match(/Fat\s+Carbs\s+Prot\s+Cals\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)/);
  if (tm) {
    total = { fat: parseFloat(tm[1]), carbs: parseFloat(tm[2]),
              protein: parseFloat(tm[3]), calories: parseInt(tm[4]) };
  }

  // Per-meal
  const meals = {};
  const mealRe = /(Breakfast|Lunch|Dinner|Snacks\/Other)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)/g;
  let m;
  while ((m = mealRe.exec(text)) !== null) {
    const key = m[1].toLowerCase().replace("/", "_");
    meals[key] = { fat: parseFloat(m[2]), carbs: parseFloat(m[3]),
                   protein: parseFloat(m[4]), calories: parseInt(m[5]) };
  }

  const today = new Date().toISOString().slice(0, 10);
  return { date: today, total, meals, updated_at: new Date().toISOString() };
}

async function postToProxy(data) {
  const resp = await fetch(PROXY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
    body: JSON.stringify(data)
  });
  if (!resp.ok) throw new Error(`Proxy error: HTTP ${resp.status}`);
  return resp.json();
}

// Handle "Sync now" from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "syncNow") {
    syncDiary()
      .then(() => chrome.storage.local.get("lastData", (s) =>
        sendResponse({ ok: true, data: s.lastData })))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // async response
  }
});
