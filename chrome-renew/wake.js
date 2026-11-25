// Runs only in an isolated content-script world on loopback pages.
// No credentials, pairing codes, or provider responses enter the page.
if (location.hostname === "127.0.0.1" && location.pathname === "/" &&
    document.querySelector('meta[name="tpscraper-dashboard"][content="1"]')) {
  const wake = () => chrome.runtime.sendMessage({type: "dashboard-wake"}).catch(() => {});
  void wake();
  // Cover the race between page load, worker activation and the pending request.
  for (const delay of [1500, 4000, 9000]) setTimeout(wake, delay);
}
