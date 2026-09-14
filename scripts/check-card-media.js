/**
 * 피드 카드가 결정 티켓으로 그려지는지 확인한다.
 * 사용: node scripts/check-card-media.js [베이스URL]
 * 기본값은 로컬 백엔드(http://127.0.0.1:8123).
 */
const http = require("http");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8123";
const ORIGIN = new URL(BASE).origin;
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 9366;
const OUT = path.join(os.tmpdir(), "jh-card-media");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${path.join(OUT, "profile")}`,
      "--window-size=390,800",
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  let target = null;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(500);
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
  const ev = async (expr) =>
    (await send("Runtime.evaluate", {
      expression: expr,
      awaitPromise: true,
      returnByValue: true,
    })).result?.result?.value;

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 800,
    deviceScaleFactor: 2,
    mobile: true,
  });
  await send("Browser.grantPermissions", {
    origin: ORIGIN,
    permissions: ["geolocation"],
  });
  await send("Emulation.setGeolocationOverride", {
    latitude: 37.4979,
    longitude: 127.0276,
    accuracy: 30,
  });

  const outbound = [];
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.method === "Network.requestWillBeSent") outbound.push(m.params.request.url);
  });

  await send("Page.navigate", { url: BASE + "/" });
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    if (
      await ev(
        `(()=>{const e=document.getElementById('intro');return !e||e.classList.contains('is-out')})()`
      )
    )
      break;
  }
  await ev(`document.getElementById('btn-start').click(); true`);
  for (let i = 0; i < 30; i++) {
    await sleep(400);
    if (
      await ev(`!document.getElementById('taste-stage')?.classList.contains('hidden')`)
    )
      break;
  }
  await ev(
    `(()=>{const c=[...document.querySelectorAll('#taste-step-cat .taste-cat')];c[0]?.click();c[1]?.click();return true})()`
  );
  await sleep(300);
  await ev(`document.getElementById('btn-taste-next')?.click(); true`);
  await sleep(600);
  await ev(`document.querySelector('#taste-step-tone .taste-tone')?.click(); true`);
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    if (
      await ev(`!document.getElementById('screen-feed')?.classList.contains('hidden')`)
    )
      break;
  }

  let bad = 0;
  for (let i = 0; i < 5; i++) {
    const s = await ev(`(() => {
      const photo = document.getElementById('card-media');
      return JSON.stringify({
        place: document.getElementById('card-place')?.textContent.trim(),
        kind: document.getElementById('card-menu')?.textContent.trim(),
        hero: document.getElementById('card-hero-num')?.textContent.trim(),
        cap: document.getElementById('card-hero-cap')?.textContent.trim(),
        dist: document.getElementById('card-dist')?.textContent.trim(),
        pin: !!document.querySelector('.map-pin'),
        photoOn: document.getElementById('card')?.classList.contains('has-photo'),
        photoDisplay: photo ? getComputedStyle(photo).display : 'missing',
      });
    })()`);
    const o = JSON.parse(s);
    const ticketOk =
      o.place &&
      /^\d+분$/.test(o.hero) &&
      o.dist &&
      o.dist !== "—" &&
      !o.pin &&
      (o.photoOn || o.photoDisplay === "none");
    if (!ticketOk) bad++;
    console.log(
      `${ticketOk ? "OK  " : "실패"} 카드 ${i + 1}: ${o.kind} · ${o.place} · ${o.hero} ${o.cap} · ${o.dist}`
    );
    if (i === 0) {
      const r = await send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(OUT, "card.png"), Buffer.from(r.result.data, "base64"));
    }
    await ev(`document.getElementById('btn-nope')?.click(); true`);
    await sleep(1800);
  }

  await ev(`document.querySelector('.tog[data-intent="delivery"]')?.click(); true`);
  for (let i = 0; i < 20; i++) {
    await sleep(400);
    const cap = await ev(`document.getElementById('card-hero-cap')?.textContent.trim()`);
    if (cap && cap.includes("배달")) break;
  }
  const delivery = await ev(`(() => JSON.stringify({
    place: document.getElementById('card-place')?.textContent.trim(),
    hero: document.getElementById('card-hero-num')?.textContent.trim(),
    cap: document.getElementById('card-hero-cap')?.textContent.trim(),
  }))()`);
  const d = JSON.parse(delivery);
  const deliveryOk = /^\d+분$/.test(d.hero) && /배달/.test(d.cap);
  if (!deliveryOk) bad++;
  console.log(`${deliveryOk ? "OK  " : "실패"} 배달 전환: ${d.place} · ${d.hero} ${d.cap}`);
  const r2 = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, "card-delivery.png"), Buffer.from(r2.result.data, "base64"));

  const dead = outbound.filter((u) => u.includes("staticmap.openstreetmap"));
  console.log("");
  console.log(`${bad === 0 ? "OK  " : "실패"} 티켓으로 안 그려진 카드: ${bad}개`);
  console.log(`${dead.length === 0 ? "OK  " : "실패"} 죽은 스태틱맵 요청: ${dead.length}건`);
  console.log("스크린샷: " + path.join(OUT, "card.png"));

  chrome.kill();
  process.exit(bad === 0 && dead.length === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("실패:", e.message);
  process.exit(1);
});
