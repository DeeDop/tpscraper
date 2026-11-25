const LOCAL = "http://127.0.0.1:8790";
const TOKEN = "https://takeprofit.com/api/auth/token";
let busy = false;
let restoring = null;
const ALARM = "renew";

async function isPaired(pair) {
  return (await chrome.storage.local.get("pair")).pair === pair;
}

async function disable(status, expectedPair = null) {
  if (expectedPair !== null && !(await isPaired(expectedPair))) return;
  await chrome.storage.local.remove("pair");
  await chrome.alarms.clear("renew");
  await chrome.storage.local.set({status});
}

async function deny(pair, requestId) {
  if (!(await isPaired(pair))) return;
  await fetch(LOCAL + "/failure", {
    method: "POST",
    headers: {Authorization: "Bearer " + pair, "Content-Type": "application/json"},
    body: JSON.stringify({request_id: requestId}),
    redirect: "error", signal: AbortSignal.timeout(5000)
  }).catch(() => {});
  await disable("Authorization refused or invalid. Check your TakeProfit sign-in and access permissions.", pair);
}

async function poll() {
  if (busy) return;
  busy = true;
  try {
    const {pair} = await chrome.storage.local.get("pair");
    if (!pair) return;
    const authorization = {Authorization: "Bearer " + pair};
    let status;
    try {
      status = await fetch(LOCAL + "/status", {
        headers: authorization, cache: "no-store", redirect: "error",
        signal: AbortSignal.timeout(5000)
      });
    } catch {
      if (await isPaired(pair))
        await chrome.storage.local.set({status: "Local service offline; pairing retained."});
      return;
    }
    if (status.status === 403) {
      await disable("Pairing expired. Pair again with the local service.", pair);
      return;
    }
    if (!status.ok || !(await isPaired(pair))) return;
    const request = await status.json();
    if (!request.renew || typeof request.request_id !== "string") {
      if (await isPaired(pair)) await chrome.storage.local.set({status: "Paired; local service connected. Waiting for renewal."});
      return;
    }
    let response;
    try {
      response = await fetch(TOKEN, {
        credentials: "include", cache: "no-store", redirect: "error",
        signal: AbortSignal.timeout(15000), headers: {Accept: "application/json"}
      });
    } catch {
      // A transport failure is not an entitlement denial. The local request
      // has a bounded deadline; no aggressive retries or credential fallback.
      if (await isPaired(pair))
        await chrome.storage.local.set({status: "Network unavailable; pairing retained."});
      return;
    }
    if (response.status >= 500) {
      if (await isPaired(pair))
        await chrome.storage.local.set({status: "Authorization service unavailable; pairing retained."});
      return;
    }
    if (!response.ok) {
      await deny(pair, request.request_id);
      return;
    }
    let access;
    try {
      const data = await response.json();
      if (data.success !== true || typeof data.data?.accessToken !== "string")
        throw new Error("Invalid authorization response");
      access = data.data.accessToken;
    } catch {
      await deny(pair, request.request_id);
      return;
    }
    try {
      if (!(await isPaired(pair))) return;
      const accepted = await fetch(LOCAL + "/token", {
        method: "POST", headers: {...authorization, "Content-Type": "application/json"},
        body: JSON.stringify({accessToken: access, request_id: request.request_id}),
        redirect: "error", signal: AbortSignal.timeout(5000)
      });
      if (accepted.status === 409) return;
      if (accepted.status === 403) {
        await disable("Pairing expired. Pair again with the local service.", pair);
        return;
      }
      if (accepted.status === 400) {
        await deny(pair, request.request_id);
        return;
      }
      if (accepted.ok && await isPaired(pair))
        await chrome.storage.local.set({status: "Authorized at " + new Date().toLocaleTimeString()});
    } catch {
      if (await isPaired(pair))
        await chrome.storage.local.set({status: "Local service unavailable; pairing retained."});
    } finally {
      access = undefined;
    }
  } catch {
    // Never emit response bodies or credentials into browser logs.
  } finally {
    busy = false;
  }
}

async function ensureAlarm() {
  const alarm = await chrome.alarms.get(ALARM);
  if (!alarm || alarm.periodInMinutes !== 0.5)
    await chrome.alarms.create(ALARM, {delayInMinutes: 0.5, periodInMinutes: 0.5});
}

function restore() {
  if (restoring) return restoring;
  restoring = (async () => {
    await chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
    const {pair} = await chrome.storage.local.get("pair");
    if (pair) {
      // Alarm creation may fail transiently; a dashboard wake can still poll.
      await ensureAlarm().catch(() => {});
      await poll();
    }
  })().finally(() => { restoring = null; });
  return restoring;
}
function wake() { void restore().catch(() => {}); }
// Register synchronously before doing asynchronous work so MV3 can dispatch
// events even when the service worker has been suspended.
chrome.runtime.onStartup.addListener(wake);
chrome.runtime.onInstalled.addListener(wake);
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === ALARM) wake();
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return;
  // A local dashboard can only request a wake-up, never credentials or pairing.
  // Other messages must originate from the extension itself, not a web page.
  if (message.type === "dashboard-wake") {
    try {
      const url = new URL(sender.url || "");
      if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || url.pathname !== "/") return;
    } catch { return; }
    restore().then(() => respond({ok: true}), () => respond({ok: false}));
    return true;
  }
  if (sender.tab) return;
  if (message.type === "pair" && /^[A-Za-z0-9_-]{43}$/.test(message.code || "")) {
    (async () => {
      await chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
      await chrome.storage.local.set({pair: message.code, status: "Paired; checking authorization."});
      await ensureAlarm();
      respond({ok: true});
      wake();
    })().catch(() => respond({ok: false}));
    return true;
  }
  if (message.type === "check") {
    restore().then(() => respond({ok: true}), () => respond({ok: false}));
    return true;
  }
  if (message.type === "disable") {
    disable("Disabled.").then(() => respond({ok: true}), () => respond({ok: false}));
    return true;
  }
});

// Alarms are not guaranteed to survive a browser restart or extension update.
// Reconcile stored pairing on every worker activation, not just popup clicks.
wake();
