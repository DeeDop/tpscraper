const status = document.getElementById("status");
async function render() {
  const s = await chrome.storage.local.get("status");
  status.textContent = s.status || "Not paired.";
}
document.getElementById("enable").onclick = async () => {
  const field = document.getElementById("code");
  const code = field.value.trim();
  if (!/^[A-Za-z0-9_-]{43}$/.test(code)) {
    status.textContent = "Enter the pairing code printed by your local Python process.";
    return;
  }
  field.value = "";
  await chrome.runtime.sendMessage({type:"pair",code});
  await render();
};
document.getElementById("disable").onclick = async () => {
  await chrome.runtime.sendMessage({type:"disable"});
  await render();
};
chrome.storage.onChanged.addListener(render);
render();
