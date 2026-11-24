const LOCAL = "http://127.0.0.1:8790";
const TOKEN = "https://takeprofit.com/api/auth/token";
let busy = false;
async function poll() {
  if (busy) return;
  busy = true;
  try {
    const {pair} = await chrome.storage.session.get("pair");
    if (!pair) return;
    const authorization = {Authorization: "Bearer " + pair};
    const status = await fetch(LOCAL + "/status", {
      headers: authorization, cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(5000)
    });
    if (status.status === 403) {
      await disable("Pairing expired. Pair with the new local process.");
      return;
    }
    if (!status.ok) return;
    if (!(await status.json()).renew) return;
    let access;
    try {
      const r = await fetch(TOKEN, {
        credentials: "include", cache: "no-store", redirect: "error",
        signal: AbortSignal.timeout(15000), headers: {Accept: "application/json"}
      });
      if (!r.ok) throw new Error("Authorization unavailable");
      const j = await r.json();
      if (j.success !== true || typeof j.data?.accessToken !== "string")
        throw new Error("Authorization unavailable");
      access = j.data.accessToken;
      const accepted = await fetch(LOCAL + "/token", {
        method: "POST", headers: {...authorization, "Content-Type": "application/json"},
        body: JSON.stringify({accessToken: access}), redirect: "error",
        signal: AbortSignal.timeout(5000)
      });
      if (!accepted.ok) throw new Error("Renewal rejected");
      await chrome.storage.session.set({status: "Renewed at " + new Date().toLocaleTimeString()});
    } catch {
      await fetch(LOCAL + "/failure", {
        method: "POST", headers: {...authorization, "Content-Type": "application/json"},
        body: "{}", redirect: "error", signal: AbortSignal.timeout(5000)
      }).catch(() => {});
      await disable("Renewal failed. Check TakeProfit sign-in and access permissions.");
    } finally {
      access = undefined;
    }
  } catch {
    await chrome.storage.session.set({status: "Local process unavailable; waiting."});
  } finally {
    busy = false;
  }
}
async function disable(status) {
  await chrome.storage.session.remove("pair");
  await chrome.alarms.clear("renew");
  await chrome.storage.session.set({status});
}
chrome.alarms.onAlarm.addListener(a => { if (a.name === "renew") void poll(); });
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return;
  if (message.type === "pair" && /^[A-Za-z0-9_-]{43}$/.test(message.code || "")) {
    (async () => {
      await chrome.storage.session.set({pair: message.code, status: "Paired; checking authorization."});
      await chrome.alarms.create("renew", {periodInMinutes: 0.5});
      respond({ok: true});
      void poll();
    })();
    return true;
  }
  if (message.type === "disable") {
    disable("Disabled.").then(() => respond({ok: true}));
    return true;
  }
});
