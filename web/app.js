const state = {
  meta: null,
  tasteIndex: 0,
  tasteChoices: [],
  sessionId: null,
  intent: "visit",
  weather: "clear",
  intentReason: "",
  lat: null,
  lng: null,
  locationReady: false,
  usingFallbackLoc: false,
  watchId: null,
  cards: [],
  perfect: 5,
  radius: 700,
  swiping: false,
  modeSwitching: false,
  lastReceipt: null,
};

const $ = (id) => document.getElementById(id);

const GEO_OPTS = {
  enableHighAccuracy: false, // true면 일부 환경에서 응답이 멈춤
  timeout: 8000,
  maximumAge: 30000, // 30초 캐시 허용
};

const GEO_OPTS_FORCE = {
  enableHighAccuracy: true,
  timeout: 12000,
  maximumAge: 0,
};

// 위치 거부/실패 시 첫 세션이 죽지 않도록 송도 허브 폴백
const FALLBACK_LAT = 37.3925;
const FALLBACK_LNG = 126.645;
const FALLBACK_LABEL = "송도 센트럴파크 근처(임시)";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function api(path, opts = {}) {
  const retries = opts.retries ?? 2;
  const { retries: _r, ...fetchOpts } = opts;
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(path, {
        headers: {
          "Content-Type": "application/json",
          ...(fetchOpts.headers || {}),
        },
        ...fetchOpts,
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    } catch (err) {
      lastErr = err;
      if (i < retries) await sleep(1200 * (i + 1));
    }
  }
  throw lastErr;
}

function useFallbackLocation(reason) {
  state.lat = FALLBACK_LAT;
  state.lng = FALLBACK_LNG;
  state.locationReady = true;
  state.usingFallbackLoc = true;
  setLocStatus(
    `${reason} → ${FALLBACK_LABEL}로 시작해요. 가능하면 「위치 다시 가져오기」를 눌러 주세요.`,
    false
  );
  const startBtn = $("btn-start");
  if (startBtn) startBtn.disabled = false;
}

function show(id) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
  $(id).classList.remove("hidden");
  const scrollable = id === "screen-done" || id === "screen-onboard";
  document.body.classList.toggle("allow-scroll", scrollable);
  document.documentElement.classList.toggle("allow-scroll", scrollable);
  if (scrollable) {
    window.scrollTo(0, 0);
    const screen = $(id);
    if (screen) screen.scrollTop = 0;
  }
}

function setLocStatus(text, ok = false) {
  const el = $("loc-status");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("ok", ok);
  el.classList.toggle("err", !ok && text.includes("실패"));
}

function setToggleUI(intent) {
  document.querySelectorAll(".tog").forEach((b) => {
    b.classList.toggle("on", b.dataset.intent === intent);
  });
  const reason = $("intent-reason");
  if (!reason) return;
  if (state.intentReason) {
    reason.textContent = state.intentReason;
    reason.classList.remove("hidden");
  } else {
    reason.classList.add("hidden");
  }
}

function haversineM(lat1, lng1, lat2, lng2) {
  const r = 6371000;
  const toR = (d) => (d * Math.PI) / 180;
  const p1 = toR(lat1);
  const p2 = toR(lat2);
  const dp = toR(lat2 - lat1);
  const dl = toR(lng2 - lng1);
  const a =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

function applyPosition(coords) {
  const prevLat = state.lat;
  const prevLng = state.lng;
  state.lat = coords.latitude;
  state.lng = coords.longitude;
  state.locationReady = true;
  state.usingFallbackLoc = false;
  const acc = Math.round(coords.accuracy || 0);
  setLocStatus(
    `현재 위치 확인 · 정확도 ±${acc}m (${state.lat.toFixed(5)}, ${state.lng.toFixed(5)})`,
    true
  );
  $("btn-start").disabled = false;

  if (
    state.sessionId &&
    prevLat != null &&
    haversineM(prevLat, prevLng, state.lat, state.lng) >= 50
  ) {
    refreshFeed().then(renderCard).catch(console.error);
  }
}

function requestLocation(force = false) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      useFallbackLocation("이 브라우저는 위치를 지원하지 않아요");
      resolve({ latitude: FALLBACK_LAT, longitude: FALLBACK_LNG });
      return;
    }
    setLocStatus("현재 위치 확인 중…");
    const opts = force ? GEO_OPTS_FORCE : GEO_OPTS;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        applyPosition(pos.coords);
        resolve(pos.coords);
      },
      (err) => {
        if (state.locationReady && state.lat != null && state.lng != null) {
          console.warn("geo refresh failed, using cached", err);
          resolve({ latitude: state.lat, longitude: state.lng });
          return;
        }
        const reason =
          err.code === 1
            ? "위치 권한이 없어요"
            : "위치를 가져오지 못했어요";
        useFallbackLocation(reason);
        resolve({ latitude: FALLBACK_LAT, longitude: FALLBACK_LNG });
      },
      opts
    );
  });
}

function startWatchingLocation() {
  if (!navigator.geolocation || state.watchId != null) return;
  state.watchId = navigator.geolocation.watchPosition(
    (pos) => applyPosition(pos.coords),
    () => {},
    { enableHighAccuracy: false, maximumAge: 15000, timeout: 20000 }
  );
}

async function applySmartIntent() {
  const override = $("weather")?.value || "";
  try {
    const q = new URLSearchParams();
    if (override) q.set("weather", override);
    if (state.lat != null && state.lng != null) {
      q.set("lat", String(state.lat));
      q.set("lng", String(state.lng));
    }
    const ctx = await api(`/v1/context?${q}`);
    state.weather = ctx.weather || state.weather || "clear";
    state.intent = ctx.suggested_intent || state.intent;
    state.intentReason = ctx.reason || "";
    setToggleUI(state.intent);
    const ws = $("weather-status");
    if (ws) {
      const label = {
        clear: "맑음",
        rain: "비",
        snow: "눈",
        hot: "더움",
        cold: "추움",
      }[state.weather] || state.weather;
      const src = ctx.weather_meta?.source === "open-meteo" ? "실날씨" : "설정";
      const temp =
        ctx.weather_meta?.temp_c != null
          ? ` · ${Math.round(ctx.weather_meta.temp_c)}°C`
          : "";
      ws.textContent = `날씨 ${label}${temp} (${src}) → ${
        state.intent === "delivery" ? "배달" : "방문"
      } 추천`;
    }
  } catch (err) {
    console.warn("smart intent skipped", err);
    state.intentReason = "";
    setToggleUI(state.intent);
    const ws = $("weather-status");
    if (ws) ws.textContent = "날씨 확인 실패 — 맑음 기준으로 진행";
  }
}

const TASTE_MENU_POOL = [
  { key: "jjajang", label: "짜장면", category: "chinese", image: "https://images.unsplash.com/photo-1582878826629-29b7ad1cdc43?w=600&q=80" },
  { key: "jjamppong", label: "짬뽕", category: "chinese", image: "/static/tastes/jjamppong.jpg" },
  { key: "sundaeguk", label: "순대국", category: "korean", image: "/static/tastes/sundaeguk.jpg" },
  { key: "gukbap", label: "국밥", category: "korean", image: "/static/tastes/gukbap.jpg" },
  { key: "bibimbap", label: "비빔밥", category: "korean", image: "https://images.unsplash.com/photo-1553163147-622ab57be1c7?w=600&q=80" },
  { key: "tteokbokki", label: "떡볶이", category: "korean", image: "https://images.unsplash.com/photo-1635363638580-c2809d049eee?w=600&q=80" },
  { key: "kalguksu", label: "칼국수", category: "noodle", image: "/static/tastes/kalguksu.jpg" },
  { key: "naengmyeon", label: "냉면", category: "noodle", image: "https://images.unsplash.com/photo-1455619452474-d2be8b1e70cd?w=600&q=80" },
  { key: "ramen", label: "라멘", category: "japanese", image: "https://images.unsplash.com/photo-1617093727343-374698b1b08d?w=600&q=80" },
  { key: "sushi", label: "초밥", category: "japanese", image: "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=600&q=80" },
  { key: "donkatsu", label: "돈가스", category: "japanese", image: "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=600&q=80" },
  { key: "udon", label: "우동", category: "japanese", image: "/static/tastes/udon.jpg" },
  { key: "pork", label: "삼겹살", category: "meat", image: "/static/tastes/pork.jpg" },
  { key: "galbi", label: "갈비", category: "meat", image: "/static/tastes/galbi.jpg" },
  { key: "chicken", label: "치킨", category: "meat", image: "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=600&q=80" },
  { key: "pizza", label: "피자", category: "western", image: "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=600&q=80" },
  { key: "pasta", label: "파스타", category: "western", image: "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=600&q=80" },
  { key: "burger", label: "햄버거", category: "western", image: "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=600&q=80" },
];

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** 시작마다 카테고리가 다른 A vs B 4쌍 랜덤 */
function sampleTastePairs(n = 4) {
  const pool = shuffle(TASTE_MENU_POOL);
  const used = new Set();
  const pairs = [];
  const pick = (avoidCat) => {
    for (const m of pool) {
      if (used.has(m.key)) continue;
      if (avoidCat && m.category === avoidCat) continue;
      return m;
    }
    return pool.find((m) => !used.has(m.key)) || null;
  };
  for (let i = 0; i < n; i++) {
    const left = pick(null);
    if (!left) break;
    used.add(left.key);
    const right = pick(left.category);
    if (!right) {
      used.delete(left.key);
      break;
    }
    used.add(right.key);
    const a = Math.random() < 0.5 ? left : right;
    const b = a === left ? right : left;
    pairs.push({
      id: `t${i + 1}`,
      prompt: "지금 더 끌리는 음식은?",
      left: { key: a.key, label: a.label, image: a.image },
      right: { key: b.key, label: b.label, image: b.image },
    });
  }
  return pairs;
}

async function onStartClick() {
  const btn = $("btn-start");
  try {
    btn.disabled = true;
    btn.textContent = "시작 중…";

    if (!state.locationReady || state.lat == null || state.lng == null) {
      btn.textContent = "위치 확인 중…";
      try {
        await Promise.race([
          requestLocation(false),
          new Promise((_, rej) =>
            setTimeout(() => rej(new Error("location timeout")), 8000)
          ),
        ]);
      } catch (_) {
        useFallbackLocation("위치 확인이 지연됐어요");
      }
    }
    if (!state.locationReady || state.lat == null || state.lng == null) {
      useFallbackLocation("위치 확인이 지연됐어요");
    }

    // 취향 페어는 클라이언트에서 매번 랜덤 (서버 캐시/구버전과 무관)
    state.meta = { ...(state.meta || {}), taste_pairs: sampleTastePairs(4) };
    $("start-panel").classList.add("hidden");
    $("taste-stage").classList.remove("hidden");
    const hero = document.querySelector(".brand-hero");
    if (hero) hero.classList.add("compact");
    btn.disabled = false;
    btn.textContent = "시작하기";
    state.tasteIndex = 0;
    state.tasteChoices = [];
    renderTaste();
    try {
      $("taste-stage").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (_) {}
    applySmartIntent();
  } catch (err) {
    console.error(err);
    btn.disabled = false;
    btn.textContent = "시작하기";
    setLocStatus(
      !state.locationReady
        ? "딱 맞는 맛집을 위해 현재 위치가 필요해요. 「위치 다시 가져오기」를 눌러 주세요."
        : "시작에 실패했어요. 다시 눌러 주세요.",
      false
    );
  }
}

async function init() {
  state.meta = await api("/v1/meta");
  $("btn-start").disabled = true;
  $("btn-start").onclick = onStartClick;
  $("btn-retry-loc").onclick = () => requestLocation(true).catch(() => {});
  $("btn-nope").onclick = () => swipe("nope");
  $("btn-go").onclick = () => swipe("lets_go");
  $("btn-again").onclick = () => location.reload();
  $("btn-share").onclick = () => shareReceipt();
  $("btn-copy").onclick = () => copyShareLink();
  const duoBtn = $("btn-duo");
  if (duoBtn) duoBtn.onclick = () => createDuoInvite();
  const duoDone = $("btn-duo-done");
  if (duoDone) duoDone.onclick = () => createDuoInvite();
  const reloadBtn = $("btn-reload-feed");
  if (reloadBtn) {
    reloadBtn.onclick = async () => {
      try {
        await ensureFreshLocation();
        // 강제 재시드: session 재시작
        const data = await api("/v1/session", {
          method: "POST",
          body: JSON.stringify({
            lat: state.lat,
            lng: state.lng,
            intent: state.intent,
            weather: state.weather,
            taste: state.tasteChoices,
          }),
        });
        applyFeed(data);
        setToggleUI(state.intent);
        renderCard();
      } catch (err) {
        console.error(err);
      }
    };
  }
  $("weather").onchange = () => applySmartIntent().catch(console.error);

  document.querySelectorAll(".tog").forEach((btn) => {
    btn.onclick = async () => {
      if (state.swiping || state.modeSwitching) return;
      const next = btn.dataset.intent;
      if (!next || next === state.intent) return;
      state.modeSwitching = true;
      state.intent = next;
      state.intentReason = "";
      setToggleUI(state.intent);
      // 덱을 비우지 않음 — 카드 유지한 채 반경만 즉시 교체
      try {
        await refreshFeed();
        renderCard();
      } catch (err) {
        console.error(err);
      } finally {
        state.modeSwitching = false;
      }
    };
  });

  setupSwipeGestures();
  setupLongPress();
  setupInstallPwa();
  await requestLocation().catch(() => {});
  startWatchingLocation();
  await applySmartIntent().catch(console.error);
}

async function ensureFreshLocation() {
  if (state.locationReady && state.lat != null && state.lng != null) {
    return { latitude: state.lat, longitude: state.lng };
  }
  try {
    await requestLocation(false);
  } catch (_) {
    useFallbackLocation("위치를 가져오지 못했어요");
  }
  if (!state.locationReady || state.lat == null || state.lng == null) {
    useFallbackLocation("위치를 가져오지 못했어요");
  }
  return { latitude: state.lat, longitude: state.lng };
}

function renderTaste() {
  const pairs = state.meta.taste_pairs;
  if (state.tasteIndex >= pairs.length) {
    startSession();
    return;
  }
  const p = pairs[state.tasteIndex];
  $("taste-prompt").textContent = p.prompt;
  $("taste-progress").textContent = `${state.tasteIndex + 1} / ${pairs.length}`;
  const left = $("taste-left");
  const right = $("taste-right");
  left.style.backgroundImage = `linear-gradient(rgba(0,0,0,.25),rgba(0,0,0,.35)), url('${p.left.image}')`;
  right.style.backgroundImage = `linear-gradient(rgba(0,0,0,.25),rgba(0,0,0,.35)), url('${p.right.image}')`;
  left.textContent = p.left.label;
  right.textContent = p.right.label;
  left.onclick = () => pickTaste(p.left.key);
  right.onclick = () => pickTaste(p.right.key);
}

function pickTaste(key) {
  state.tasteChoices.push(key);
  state.tasteIndex += 1;
  renderTaste();
}

async function startSession() {
  await ensureFreshLocation();
  const data = await api("/v1/session", {
    method: "POST",
    body: JSON.stringify({
      lat: state.lat,
      lng: state.lng,
      intent: state.intent,
      weather: state.weather,
      taste: state.tasteChoices,
    }),
  });
  applyFeed(data);
  show("screen-feed");
  setToggleUI(state.intent);
  renderCard();
}

async function refreshFeed() {
  if (!state.sessionId) return;
  await ensureFreshLocation();
  const q = new URLSearchParams({
    session_id: state.sessionId,
    intent: state.intent,
    weather: state.weather,
    lat: String(state.lat),
    lng: String(state.lng),
  });
  const data = await api(`/v1/feed?${q}`);
  applyFeed(data);
}

function applyFeed(data) {
  state.sessionId = data.session_id;
  state.cards = data.cards || [];
  state.perfect = data.perfect_slots_left;
  state.radius = data.effective_radius_m;
  if (data.intent) state.intent = data.intent;
  $("feed-copy").textContent = data.copy || "오늘 점심은 그냥여기 어때?";
  if ($("tier-label")) $("tier-label").textContent = data.tier_label || data.tier || "—";
  $("radius-label").textContent = `내 위치 · 반경 ${state.radius}m`;
  $("slots-label").textContent = `${state.perfect}/5`;
  if ($("source-label")) {
    const srcMap = {
      hub_seed: "송도 큐레이션",
      hub_seed_anchored: "송도 · 내위치",
      "hub+kakao": "송도 + 주변 실상호",
      kakao: "주변 실상호",
      seed_fallback: "라이트 폴백",
    };
    $("source-label").textContent = srcMap[data.inventory_source] || data.inventory_source || "";
  }
}

function currentCard() {
  return state.cards[0] || null;
}

function mapStaticUrl(lat, lng) {
  return (
    "https://staticmap.openstreetmap.de/staticmap.php" +
    `?center=${lat},${lng}&zoom=16&size=600x900&maptype=mapnik` +
    `&markers=${lat},${lng},red-pushpin`
  );
}

function clearMapChrome(media) {
  media.classList.remove("is-map", "is-map-css");
  const pin = media.querySelector(".map-pin");
  if (pin) pin.remove();
  const badge = $("map-badge");
  if (badge) {
    badge.classList.add("hidden");
    badge.textContent = "";
  }
}

function showMapFallback(card) {
  const media = $("card-media");
  const badge = $("map-badge");
  clearMapChrome(media);
  media.classList.add("is-map");
  const lat = card.lat;
  const lng = card.lng;
  const distLabel =
    card.eta_label ||
    (card.distance_m != null ? `${card.distance_m}m` : "근처");

  if (badge) {
    badge.textContent = `지도 · ${distLabel}`;
    badge.classList.remove("hidden");
  }

  if (lat == null || lng == null) {
    media.classList.add("is-map-css");
    media.style.backgroundImage = "";
    const pin = document.createElement("div");
    pin.className = "map-pin";
    pin.textContent = "📍";
    media.appendChild(pin);
    return;
  }

  const url = mapStaticUrl(lat, lng);
  const probe = new Image();
  probe.onload = () => {
    media.style.backgroundImage = `url('${url}')`;
  };
  probe.onerror = () => {
    media.classList.add("is-map-css");
    media.style.backgroundImage = "";
    if (!media.querySelector(".map-pin")) {
      const pin = document.createElement("div");
      pin.className = "map-pin";
      pin.textContent = "📍";
      media.appendChild(pin);
    }
  };
  probe.src = url;
}

function setCardMedia(card) {
  const media = $("card-media");
  clearMapChrome(media);
  const url = (card.image_url || "").trim();
  const looksFake =
    !url ||
    url.includes("picsum.photos") ||
    card.has_photo === false;

  if (looksFake) {
    showMapFallback(card);
    return;
  }

  const probe = new Image();
  probe.onload = () => {
    media.style.backgroundImage = `url('${url}')`;
  };
  probe.onerror = () => showMapFallback(card);
  probe.src = url;
}

function renderCard() {
  const card = currentCard();
  const empty = $("empty");
  const el = $("card");
  if (!card) {
    el.classList.add("hidden");
    empty.classList.remove("hidden");
    const msg = $("empty-msg");
    if (msg) {
      msg.textContent =
        "근처에 보여줄 곳이 없어요. 아래 버튼으로 다시 불러오거나, 방문/배달을 바꿔 보세요.";
    } else {
      empty.textContent =
        "근처에 보여줄 곳이 없어요. 다시 불러오기를 눌러 주세요.";
    }
    return;
  }
  empty.classList.add("hidden");
  el.classList.remove("hidden");
  el.classList.toggle("gold", !!card.is_gold);
  $("gold-badge").classList.toggle("hidden", !card.is_gold);
  setCardMedia(card);
  $("card-place").textContent = card.place_name;
  $("card-menu").textContent = card.menu_name;
  $("card-eta").textContent = card.eta_label;
  $("card-tag").textContent = card.taste_match
    ? "#취향맞춤"
    : card.hashtag || (card.source === "kakao" ? "#근처_실상호" : "#그냥여기");
  $("detail").classList.add("hidden");
  const goLabel = $("btn-go")?.querySelector(".go-label");
  if (goLabel) {
    goLabel.textContent = "그냥여기";
  }
  el.style.transform = "";
  el.style.opacity = "1";
}

function spawnConfetti() {
  const layer = $("confetti-layer");
  layer.innerHTML = "";
  const colors = ["#ffd166", "#fff", "#ff6a3d", "#ff9f1c", "#d62828"];
  for (let i = 0; i < 42; i++) {
    const p = document.createElement("span");
    p.className = "confetti-piece";
    p.style.left = `${Math.random() * 100}%`;
    p.style.background = colors[i % colors.length];
    p.style.animationDelay = `${Math.random() * 0.25}s`;
    p.style.setProperty("--dx", `${(Math.random() - 0.5) * 160}px`);
    p.style.setProperty("--rot", `${Math.random() * 720 - 360}deg`);
    layer.appendChild(p);
  }
}

function openHandoff(handoff) {
  const url = handoff.url;
  if (!url) return false;
  try {
    const win = window.open(url, "_blank", "noopener");
    if (!win) {
      window.location.href = url;
      return true;
    }
    return true;
  } catch {
    window.location.href = url;
    return false;
  }
}

function showMatchThenHandoff(data) {
  const flash = $("match-flash");
  $("match-sub").textContent = `${data.place_name} · ${data.menu_name}`;
  spawnConfetti();
  flash.classList.remove("hidden");

  // 배민/지도 자동 점프 없음 — 완료 화면에서 지도 버튼으로 열기
  window.setTimeout(() => {
    flash.classList.add("hidden");
    showDone(data);
  }, 900);
}

async function swipe(action) {
  const card = currentCard();
  if (!card || state.swiping) return;
  state.swiping = true;
  try {
    const data = await api("/v1/swipe", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        card_id: card.card_id,
        menu_id: card.menu_id,
        action,
      }),
    });
    if (action === "lets_go") {
      showMatchThenHandoff(data);
      return;
    }
    applyFeed(data);
    renderCard();
  } finally {
    state.swiping = false;
  }
}

function setShareStatus(text) {
  const el = $("share-status");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}

async function createDuoInvite() {
  try {
    if (!state.locationReady || state.lat == null) {
      await ensureFreshLocation();
    }
    if (!state.tasteChoices?.length) {
      alert("취향 선택 후 Duo를 만들 수 있어요.");
      return;
    }
    const room = await api("/v1/duo", {
      method: "POST",
      body: JSON.stringify({
        lat: state.lat,
        lng: state.lng,
        intent: state.intent,
        weather: state.weather,
        taste: state.tasteChoices,
        host_name: "나",
      }),
    });
    const url = room.invite_url || `${location.origin}${room.invite_path}`;
    try {
      await navigator.clipboard.writeText(url);
      alert(`Duo 초대 링크를 복사했어요!\n카톡에 붙여넣기 하세요.\n\n${url}`);
    } catch {
      prompt("이 링크를 친구에게 보내세요", url);
    }
  } catch (err) {
    console.error(err);
    const msg = String(err?.message || err || "");
    if (msg.includes("404") || msg.includes("Not Found")) {
      alert(
        "Duo API가 없어요. 서버를 재시작해 주세요.\n\nPowerShell에서:\ncd backend\n.\\run.bat"
      );
      return;
    }
    alert("Duo 방 만들기에 실패했어요.\n" + msg.slice(0, 160));
  }
}

async function ensureReceipt(data) {
  if (data?.receipt?.share_url) {
    state.lastReceipt = data.receipt;
    return data.receipt;
  }
  if (state.lastReceipt?.share_url) return state.lastReceipt;
  const persona = data.persona || {};
  const created = await api("/v1/share/receipt", {
    method: "POST",
    body: JSON.stringify({
      title: data.receipt_title || persona.title || "본능 100% 그냥여기 마스터",
      place_name: data.place_name,
      menu_name: data.menu_name,
      intent: state.intent,
      tier: data.tier || "",
      session_id: state.sessionId,
      sub_text: persona.sub_text || "",
      theme: persona.theme || "bg_basic",
      match_reason: persona.match_reason || "",
      persona_id: persona.id || "",
      sticker: persona.sticker || "🛋️",
      asset_id: persona.asset_id || persona.theme || "bg_basic",
    }),
  });
  state.lastReceipt = created;
  return created;
}

async function shareReceipt() {
  try {
    const receipt = state.lastReceipt;
    if (!receipt) {
      setShareStatus("공유할 영수증이 없어요.");
      return;
    }
    const payload = {
      title: "식탐 영수증 · 그냥여기",
      text: receipt.share_text,
      url: receipt.share_url,
    };
    if (navigator.share) {
      await navigator.share(payload);
      setShareStatus("공유했어요!");
      return;
    }
    await navigator.clipboard.writeText(receipt.share_text);
    setShareStatus("카톡에 붙여넣기 하세요 — 링크 복사됨");
  } catch (err) {
    if (err && err.name === "AbortError") return;
    try {
      await navigator.clipboard.writeText(state.lastReceipt?.share_text || "");
      setShareStatus("링크 텍스트를 복사했어요");
    } catch {
      setShareStatus("공유에 실패했어요. 링크 복사를 눌러 주세요.");
    }
  }
}

async function copyShareLink() {
  try {
    const receipt = state.lastReceipt;
    if (!receipt) {
      setShareStatus("공유할 영수증이 없어요.");
      return;
    }
    await navigator.clipboard.writeText(receipt.share_text);
    setShareStatus("복사 완료 — 카톡에 붙여넣기");
  } catch {
    setShareStatus("복사 실패. 브라우저 권한을 확인해 주세요.");
  }
}

function showDone(data) {
  show("screen-done");
  $("done-sub").textContent = `${data.place_name} · ${data.menu_name}`;
  const persona = data.persona || {};
  const title = data.receipt_title || persona.title || "본능 100% 그냥여기 마스터";
  $("receipt-title").textContent = title;
  $("receipt-sub").textContent = persona.sub_text || data.receipt?.sub_text || "";
  $("receipt-sticker").textContent =
    persona.sticker || data.receipt?.sticker || "🛋️";
  $("receipt-place").textContent = data.place_name || "";
  $("receipt-menu").textContent = data.menu_name || "";
  $("receipt-reason").textContent =
    persona.match_reason || data.receipt?.match_reason || "근처 매칭 완료";
  const theme =
    persona.asset_id ||
    persona.theme ||
    data.receipt?.asset_id ||
    data.receipt?.theme ||
    "bg_basic";
  const card = $("receipt");
  card.className = `receipt-card theme-${theme}`;
  const link = $("handoff-link");
  link.href = data.handoff.url;
  link.textContent = data.handoff.cta || "지도에서 보기";
  const note = $("handoff-note");
  if (note) {
    if (data.handoff.note) {
      note.textContent = data.handoff.note;
      note.classList.remove("hidden");
    } else {
      note.textContent = "";
      note.classList.add("hidden");
    }
  }
  setShareStatus("");
  ensureReceipt(data)
    .then(() => setShareStatus("친구에게 자랑할 준비 완료"))
    .catch(() => setShareStatus("공유 링크 생성 실패"));
}

function setupSwipeGestures() {
  const el = $("card");
  let startX = 0;
  let dx = 0;
  let active = false;

  const onStart = (x) => {
    active = true;
    startX = x;
    dx = 0;
  };
  const onMove = (x) => {
    if (!active) return;
    dx = x - startX;
    el.style.transform = `translateX(${dx}px) rotate(${dx / 40}deg)`;
    el.style.opacity = String(Math.max(0.4, 1 - Math.abs(dx) / 300));
  };
  const onEnd = async () => {
    if (!active) return;
    active = false;
    if (dx > 100) await swipe("lets_go");
    else if (dx < -100) await swipe("nope");
    else {
      el.style.transform = "";
      el.style.opacity = "1";
    }
  };

  el.addEventListener("touchstart", (e) => onStart(e.touches[0].clientX), {
    passive: true,
  });
  el.addEventListener("touchmove", (e) => onMove(e.touches[0].clientX), {
    passive: true,
  });
  el.addEventListener("touchend", onEnd);
  el.addEventListener("mousedown", (e) => onStart(e.clientX));
  window.addEventListener("mousemove", (e) => onMove(e.clientX));
  window.addEventListener("mouseup", onEnd);
}

function setupLongPress() {
  const el = $("card");
  let timer = null;
  const showDetail = () => {
    const card = currentCard();
    if (!card) return;
    const d = $("detail");
    d.innerHTML = `
      <strong>${card.place_name}</strong>
      <span>영업 ${card.hours}</span>
      <span>평점 ${card.rating}</span>
      <span>${card.review}</span>
      <span>배달민감도 ${card.delivery_sensitivity}</span>
    `;
    d.classList.remove("hidden");
  };
  const hide = () => $("detail").classList.add("hidden");

  el.addEventListener(
    "touchstart",
    () => {
      timer = setTimeout(showDetail, 450);
    },
    { passive: true }
  );
  el.addEventListener("touchend", () => {
    clearTimeout(timer);
    hide();
  });
  el.addEventListener("mousedown", () => {
    timer = setTimeout(showDetail, 450);
  });
  el.addEventListener("mouseup", () => {
    clearTimeout(timer);
    hide();
  });
}

function setupInstallPwa() {
  const btn = $("btn-install");
  if (!btn) return;

  let deferred = null;
  const showBtn = () => btn.classList.remove("hidden");
  const hideBtn = () => btn.classList.add("hidden");

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e;
    showBtn();
  });

  window.addEventListener("appinstalled", () => {
    deferred = null;
    hideBtn();
    setLocStatus("홈 화면에 추가됐어요. 앱처럼 실행하면 됩니다.", true);
  });

  // iOS / 이미 설치됨: 안내만
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;
  if (isStandalone) {
    hideBtn();
  }

  btn.onclick = async () => {
    if (deferred) {
      deferred.prompt();
      try {
        await deferred.userChoice;
      } catch (_) {}
      deferred = null;
      hideBtn();
      return;
    }
    const ua = navigator.userAgent || "";
    const ios = /iPhone|iPad|iPod/i.test(ua);
    alert(
      ios
        ? "Safari 하단 공유 버튼 → 「홈 화면에 추가」를 눌러 주세요."
        : "브라우저 메뉴에서 「앱 설치」 또는 「홈 화면에 추가」를 선택해 주세요.\n\n바로 쓰기: https://justthis.co.kr"
    );
  };

  // Android Chrome 외 환경에서도 버튼은 보이게 (수동 안내)
  if (!isStandalone && !/CriOS/i.test(navigator.userAgent)) {
    setTimeout(() => {
      if (!deferred) showBtn();
    }, 1200);
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch((err) => {
      console.warn("SW register failed", err);
    });
  }
}

init().catch((err) => {
  console.error(err);
  const local =
    location.hostname === "localhost" || location.hostname === "127.0.0.1";
  alert(
    local
      ? "서버 연결 실패. backend를 먼저 실행하세요."
      : "서버가 깨어나는 중일 수 있어요. 10초 뒤 새로고침 해 주세요."
  );
  setLocStatus(
    local
      ? "서버 연결 실패"
      : "잠시 후 새로고침 하면 됩니다 (첫 접속은 30~60초 걸릴 수 있어요)",
    false
  );
  const startBtn = $("btn-start");
  if (startBtn) {
    startBtn.disabled = false;
    startBtn.textContent = "다시 시도";
    startBtn.onclick = () => location.reload();
  }
});
