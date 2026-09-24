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
  const visitState = await ev(`(() => JSON.stringify({
    empty: !document.getElementById('empty')?.classList.contains('hidden'),
    adjust: !document.getElementById('adjust-sheet')?.classList.contains('hidden'),
    progress: document.getElementById('feed-progress')?.textContent.trim(),
  }))()`);
  const vs = JSON.parse(visitState);
  if (vs.empty) {
    console.log("OK  방문 빈 결과: 가상 식당을 붙이지 않음");
  } else {
    for (let i = 0; i < 3; i++) {
      const s = await ev(`(() => {
        const photo = document.getElementById('card-media');
        return JSON.stringify({
          title: document.getElementById('card-title')?.textContent.trim(),
          sub: document.getElementById('card-sub')?.textContent.trim(),
          dist: document.getElementById('card-fact1-val')?.textContent.trim(),
          price: document.getElementById('card-fact2-val')?.textContent.trim(),
          pin: !!document.querySelector('.map-pin'),
          photoOn: document.getElementById('card')?.classList.contains('has-photo'),
          photoHidden: photo?.classList.contains('hidden'),
          hero: document.getElementById('card-hero-num')?.textContent || '',
          progress: document.getElementById('feed-progress')?.textContent.trim(),
          pass: document.getElementById('btn-nope')?.textContent.trim(),
        });
      })()`);
      const o = JSON.parse(s);
      const ticketOk =
        o.title &&
        o.dist &&
        o.dist !== "—" &&
        !o.pin &&
        !o.hero &&
        (o.photoHidden || o.photoOn) &&
        o.progress.includes(`${i + 1}/3`) &&
        /다른 가게|다른 메뉴/.test(o.pass);
      if (!ticketOk) bad++;
      console.log(
        `${ticketOk ? "OK  " : "실패"} 방문 ${i + 1}/3: ${o.sub} · ${o.title} · ${o.dist} · ${o.price} · ${o.progress}`
      );
      if (i === 0) {
        const r = await send("Page.captureScreenshot", { format: "png" });
        fs.writeFileSync(path.join(OUT, "card.png"), Buffer.from(r.result.data, "base64"));
      }
      await ev(`document.getElementById('btn-nope')?.click(); true`);
      await sleep(1800);
    }
    const adjustOn = await ev(
      `!document.getElementById('adjust-sheet')?.classList.contains('hidden')`
    );
    if (!adjustOn) bad++;
    console.log(`${adjustOn ? "OK  " : "실패"} 3장 거절 후 조정 시트`);
  }

  // 배달은 프랜차이즈 브랜드 카드 — 거리·ETA가 아니라 예산과 주문 채널을 보여준다
  await ev(`document.querySelector('.tog[data-intent="delivery"]')?.click(); true`);
  for (let i = 0; i < 25; i++) {
    await sleep(400);
    const ready = await ev(
      `document.getElementById('btn-nope')?.textContent.trim() === '다른 후보'`
    );
    if (ready) break;
  }
  const delivery = await ev(`(() => JSON.stringify({
    title: document.getElementById('card-title')?.textContent.trim(),
    sub: document.getElementById('card-sub')?.textContent.trim(),
    f1k: document.getElementById('card-fact1-key')?.textContent.trim(),
    f1v: document.getElementById('card-fact1-val')?.textContent.trim(),
    pass: document.getElementById('btn-nope')?.textContent.trim(),
    go: document.getElementById('btn-go')?.textContent.trim(),
    radiusHidden: document.getElementById('visit-radius')?.classList.contains('hidden'),
  }))()`);
  const d = JSON.parse(delivery);
  const deliveryOk =
    d.title &&
    d.f1k === "가격" &&
    /예상/.test(d.f1v) &&
    d.pass === "다른 후보" &&
    d.go === "여기로 할게" &&
    d.radiusHidden;
  if (!deliveryOk) bad++;
  console.log(
    `${deliveryOk ? "OK  " : "실패"} 배달 카드: ${d.title} · ${d.sub} · ${d.f1v} · ${d.f2v}`
  );
  const r2 = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, "card-delivery.png"), Buffer.from(r2.result.data, "base64"));

  // 마지막 한 걸음 — 주문 버튼이 브랜드 자사 주문 페이지로 나가야 한다
  await ev(`document.getElementById('btn-go')?.click(); true`);
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    if (await ev(`!document.getElementById('screen-done')?.classList.contains('hidden')`))
      break;
  }
  const done = await ev(`(() => {
    const a = document.getElementById('handoff-link');
    const n = document.getElementById('handoff-note');
    return JSON.stringify({
      href: a?.getAttribute('href') || '',
      label: a?.textContent.trim() || '',
      note: n?.classList.contains('hidden') ? '' : n?.textContent.trim(),
    });
  })()`);
  const h = JSON.parse(done);
  const known = [
    "kyochon.com","bbq.co.kr","nenechicken.com","pelicana.co.kr","kfckorea.com",
    "dominos.co.kr","pizzahut.co.kr","pizzamaru.co.kr","banolimpizza.com",
    "mrpizza.co.kr","burgerking.co.kr","lotteeatz.com","hsd.co.kr","paris.co.kr",
  ];
  const handoffOk = known.some((dm) => h.href.includes(dm)) && /주문/.test(h.label);
  if (!handoffOk) bad++;
  console.log(`${handoffOk ? "OK  " : "실패"} 배달 핸드오프: "${h.label}" → ${h.href}`);
  if (h.note) console.log(`     안내: ${h.note}`);
  const meal = await ev(`(() => JSON.stringify({
    hidden: document.getElementById('meal-prompt')?.classList.contains('hidden'),
    title: document.querySelector('#meal-prompt .meal-prompt-title')?.textContent.trim() || '',
    yes: !!document.getElementById('btn-meal-yes'),
    handoffFirst: (() => {
      const box = document.querySelector('.done-box');
      if (!box) return false;
      const kids = [...box.children].map((el) => el.id);
      return kids.indexOf('handoff-link') < kids.indexOf('meal-prompt') &&
        kids.indexOf('meal-prompt') < kids.indexOf('receipt');
    })(),
  }))()`);
  const m = JSON.parse(meal);
  const mealOk = m.hidden === false && m.yes && /드셨어요/.test(m.title) && m.handoffFirst;
  if (!mealOk) bad++;
  console.log(
    `${mealOk ? "OK  " : "실패"} 식사 확인: hidden=${m.hidden} "${m.title}" 순서=${m.handoffFirst}`
  );
  const r3 = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, "done-delivery.png"), Buffer.from(r3.result.data, "base64"));

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
