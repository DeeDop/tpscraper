const status = document.getElementById("status");
const state = document.getElementById("pair-state");
document.getElementById("version").textContent = "v" + chrome.runtime.getManifest().version;
async function render() {
  const s = await chrome.storage.local.get(["status", "pair"]);
  state.textContent = s.pair ? "Saved pairing: present" : "Saved pairing: missing";
  status.textContent = s.status || "Not paired.";
}
async function send(message) {
  try {
    const result = await chrome.runtime.sendMessage(message);
    if (!result?.ok) throw Error("Request failed");
    await render();
  } catch {
    status.textContent = "Extension unavailable. Reload it at chrome://extensions/ and try again.";
  }
}
document.getElementById("check").onclick = () => send({type:"check"});
document.getElementById("enable").onclick = async () => {
  const field = document.getElementById("code");
  const code = field.value.trim();
  if (!/^[A-Za-z0-9_-]{43}$/.test(code)) {
    status.textContent = "Enter the pairing code shown by your local tpscraper console.";
    return;
  }
  field.value = "";
  await send({type:"pair",code});
};
document.getElementById("disable").onclick = () => send({type:"disable"});
chrome.storage.onChanged.addListener(render);
render();
void send({type:"check"});
