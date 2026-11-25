const LOCAL = "http://127.0.0.1:8790";
const TOKEN = "https://takeprofit.com/api/auth/token";
let busy = false;

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
    if (!request.renew || typeof request.request_id !== "string") return;
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

async function restore() {
  await chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
  const {pair} = await chrome.storage.local.get("pair");
  if (pair) {
    if (!(await chrome.alarms.get("renew")))
      await chrome.alarms.create("renew", {periodInMinutes: 0.5});
    void poll();
  }
}
chrome.runtime.onStartup.addListener(() => void restore());
chrome.runtime.onInstalled.addListener(() => void restore());
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "renew") void poll();
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return;
  if (message.type === "pair" && /^[A-Za-z0-9_-]{43}$/.test(message.code || "")) {
    (async () => {
      await chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
      await chrome.storage.local.set({pair: message.code, status: "Paired; checking authorization."});
      await chrome.alarms.create("renew", {periodInMinutes: 0.5});
      respond({ok: true});
      void poll();
    })().catch(() => respond({ok: false}));
    return true;
  }
  if (message.type === "disable") {
    disable("Disabled.").then(() => respond({ok: true}), () => respond({ok: false}));
    return true;
  }
});
