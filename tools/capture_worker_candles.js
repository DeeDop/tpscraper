// Run manually in the Candle Stream Manager shared worker DevTools Console.
// Only copies market-data candle request and response bodies, never headers,
// cookies, tokens, other requests, or account data. No external transmission.
(() => {
  "use strict";
  if (location.hostname !== "takeprofit.com" || !location.pathname.includes("CandleStreamManager.worker")) throw Error("Inspect the TakeProfit Candle Stream Manager shared worker first.");
  if (globalThis.tpCandleCapture) { console.log("Capture already installed."); return; }
  const original = globalThis.fetch;
  const entries = [];
  const limit = 512 * 1024;
  const paths = new Set([
    "/takeprofit.marketdata.external.candle.v1.CandleStreamApi/CandleStream"
  ]);
  const encode = bytes => {
    let s = "";
    for (let i = 0; i < bytes.length; i += 8192)
      s += String.fromCharCode(...bytes.subarray(i, i+8192));
    return btoa(s);
  };
  const capture = async (response, row) => {
    if (!response.body) return;
    const reader = response.body.getReader();
    row.reader = reader;
    try {
      while (!row.stopped && row.size < limit) {
        const {done,value} = await reader.read();
        if (done) { row.complete = true; break; }
        const part = value.subarray(0,limit-row.size).slice();
        row.chunks.push(part);
        row.size += part.length;
      }
    } catch (_) {} finally { void reader.cancel().catch(()=>{}); }
  };
  const wrapper = function(input, init) {
    let row, body;
    try {
      const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url, location.href);
      const method = String(init?.method || input?.method || "GET").toUpperCase();
      if (url.origin === "https://backend.takeprofit.com" && paths.has(url.pathname) &&
          method === "POST" && entries.length < 4) {
        row = {path:url.pathname, chunks:[], size:0, complete:false, request:null};
        entries.push(row);
        body=init?.body;
        if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) {
          const bytes = body instanceof ArrayBuffer ? new Uint8Array(body) :
            new Uint8Array(body.buffer,body.byteOffset,body.byteLength);
          if (bytes.length <= 4096) row.request=encode(bytes);
        } else if (input instanceof Request && body == null) {
          input.clone().arrayBuffer().then(b => {
            if (b.byteLength <= 4096) row.request=encode(new Uint8Array(b));
          }).catch(()=>{});
        }
      }
    } catch (_) { row=null; }
    const promise = original.apply(globalThis, arguments);
    if (row) promise.then(response => {
      row.status=response.status;
      if (response.ok && (response.headers.get("content-type")||"").includes("grpc-web"))
        void capture(response.clone(),row);
    }).catch(()=>{});
    return promise;
  };
  globalThis.fetch=wrapper;
  globalThis.tpCandleCapture={
    status:()=>entries.map(r=>({service:r.path.split("/").pop(),bytes:r.size,request:!!r.request,complete:r.complete})),
    exportJSON:()=>{
      const output=entries.map(r=>{
        const bytes=new Uint8Array(r.size);
        let offset=0;
        for(const chunk of r.chunks){bytes.set(chunk,offset);offset+=chunk.length;}
        return {service:r.path.split("/").pop(),status:r.status,complete:r.complete,
                request_base64:r.request,response_base64:encode(bytes)};
      });
      return JSON.stringify(output);
    },
    stop:()=>{
      if(globalThis.fetch===wrapper)globalThis.fetch=original;
      for(const r of entries) { r.stopped=true; if(r.reader) void r.reader.cancel().catch(()=>{}); }
      delete globalThis.tpCandleCapture;
    }
  };
  console.log("Worker capture installed. Change the chart symbol/timeframe, then run tpCandleCapture.status(). To export, run copy(tpCandleCapture.exportJSON()) in this worker Console.");
})();
