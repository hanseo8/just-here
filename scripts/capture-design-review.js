/**
 * 지정 viewport만 CDP로 캡처한다.
 * 사용: node scripts/capture-design-review.js [베이스URL]
 */
const http = require("http");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8010";
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 9377;
const OUT = path.join(__dirname, "..", "docs", "design-review");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const STATES = ["photo", "brand", "nophoto", "longname", "adjust", "done"];
const VIEWPORTS = [
  { w: 390, h: 844, dpr: 2, mobile: true },
  { w: 360, h: 640, dpr: 2, mobile: true },
];

function getJSON(url) {
  return new Promise((res, rej) => {
    http
      .get(url, (r) => {
        let d = "";
        r.on("data", (c) => (d += c));
        r.on("end", () => {
          try {
            res(JSON.parse(d));
          } catch (e) {
            rej(e);
          }
        });
      })
      .on("error", rej);
  });
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${path.join(os.tmpdir(), "jh-design-review")}`,
      "--window-size=390,844",
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  let target = null;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(400);
    try {
      const list = await getJSON(`http://127.0.0.1:${PORT}/json/list`);
      target = list.find((t) => t.type === "page");
    } catch (_) {}
  }
  if (!target) throw new Error("CDP 연결 실패");

  const ws = new globalThis.WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = rej;
  });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
    }
  };
  const send = (method, params = {}) =>
    new Promise((res) => {
      const i = ++id;
      pending.set(i, res);
      ws.send(JSON.stringify({ id: i, method, params }));
    });

  await send("Page.enable");
  await send("Runtime.enable");

  const log = [];
  for (const vp of VIEWPORTS) {
    await send("Emulation.setDeviceMetricsOverride", {
      width: vp.w,
      height: vp.h,
      deviceScaleFactor: vp.dpr,
      mobile: vp.mobile,
    });
    for (const state of STATES) {
      await send("Page.navigate", { url: `${BASE}/?design=${state}` });
      await send("Page.loadEventFired");
      await sleep(state === "photo" || state === "brand" || state === "done" ? 1400 : 600);
      const shot = await send("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
        clip: { x: 0, y: 0, width: vp.w, height: vp.h, scale: 1 },
      });
      const name = `${state}-${vp.w}x${vp.h}.png`;
      const file = path.join(OUT, name);
      fs.writeFileSync(file, Buffer.from(shot.result.data, "base64"));
      const bytes = fs.statSync(file).size;
      log.push({
        file: name,
        viewport: `${vp.w}x${vp.h}`,
        dpr: vp.dpr,
        method: "CDP Emulation.setDeviceMetricsOverride + Page.captureScreenshot clip",
        bytes,
      });
      console.log(`OK  ${name}  ${bytes}B`);
    }
  }

  fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(log, null, 2));
  chrome.kill();
}

main().catch((e) => {
  console.error("실패:", e.message);
  process.exit(1);
});
