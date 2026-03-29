function fmt(data) {
  if (!data) return "No data yet";
  const t = data.total;
  if (!t) return "Parsed but no totals found";
  return `Calories: ${t.calories} kcal\nProtein: ${t.protein}g | Carbs: ${t.carbs}g | Fat: ${t.fat}g`;
}

chrome.storage.local.get(["lastSync", "lastData", "lastError"], (s) => {
  const el = document.getElementById("status");
  if (s.lastError) {
    el.className = "err";
    el.textContent = `❌ ${s.lastError}\n${s.lastSync ? "At: " + s.lastSync : ""}`;
  } else if (s.lastSync) {
    el.className = "ok";
    el.textContent = `✅ ${s.lastSync.slice(0, 16).replace("T", " ")}\n${fmt(s.lastData)}`;
  } else {
    el.textContent = "Never synced. Press button to sync now.";
  }
});

document.getElementById("sync").addEventListener("click", async () => {
  const el = document.getElementById("status");
  el.className = "";
  el.textContent = "Syncing...";

  const [bg] = await chrome.runtime.getBackgroundPage
    ? [await new Promise(r => chrome.runtime.getBackgroundPage(r))]
    : [null];

  // Send message to background service worker
  chrome.runtime.sendMessage({ action: "syncNow" }, (resp) => {
    if (chrome.runtime.lastError) {
      el.className = "err";
      el.textContent = "❌ " + chrome.runtime.lastError.message;
      return;
    }
    if (resp && resp.ok) {
      el.className = "ok";
      el.textContent = "✅ Done!\n" + fmt(resp.data);
    } else {
      el.className = "err";
      el.textContent = "❌ " + (resp && resp.error ? resp.error : "Unknown error");
    }
  });
});
