const state = {
  meta: null,
  tasteIndex: 0,
  tasteChoices: [],
  sessionId: null,
  uid: null,
  authType: "anonymous",
  intent: "visit",
  weather: "clear",
  intentReason: "",
  mealContext: "meal",
  mealHint: "",
  lat: null,
  lng: null,
  locationReady: false,
  usingFallbackLoc: false,
  watchId: null,
  cards: [],
  perfect: 5,
  radius: 700,
  packId: "",
  packRank: 0,
  packSize: 3,
  adjustNeeded: false,
  canUndo: false,
  adjustOptions: [],
  logicVersion: "",
  swiping: false,
  modeSwitching: false,
  reqSeq: 0,
  epoch: 0,
  shownKeys: {},
  inventorySource: "",
  lastAction: null,
  lastReceipt: null,
  lastDone: null,
  savedTaste: [],
  excludeCats: [],
  forceRetaste: false,
  goldUnlocked: false,
  designPreview: false,
};

const $ = (id) => document.getElementById(id);

const GEO_OPTS = {
  enableHighAccuracy: false, // true면 일부 환경에서 응답이 멈춤
  timeout: 8000,
  maximumAge: 30000, // 30초 캐시 허용
};

const GEO_OPTS_FORCE = {
  // 강제 새로고침도 highAccuracy는 피함 — 카톡/일부 안드로이드에서 콜백이 안 옴
  enableHighAccuracy: false,
  timeout: 10000,
  maximumAge: 0,
};

// 위치 거부/실패 시 첫 세션이 죽지 않도록 송도 허브 폴백
const FALLBACK_LAT = 37.3925;
const FALLBACK_LNG = 126.645;
const FALLBACK_LABEL = "송도 센트럴파크 근처(임시)";

// 진입 인트로 — init()이 끝날 때까지 덮고, 최소 시간은 채운 뒤 비킨다
const INTRO_START = Date.now();
const INTRO_MIN_MS = 1150;
const INTRO_SLOW_MS = 2600;

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function dismissIntro() {
  const el = document.getElementById("intro");
  if (!el || el.dataset.done) return;
  el.dataset.done = "1";
  const min = prefersReducedMotion() ? 0 : INTRO_MIN_MS;
  const left = Math.max(0, min - (Date.now() - INTRO_START));
  window.setTimeout(() => {
    el.classList.add("is-out");
    window.setTimeout(() => el.remove(), 560);
  }, left);
}

// 콜드스타트가 길어지면 멈춘 게 아니라는 걸 알린다
window.setTimeout(() => {
  const el = document.getElementById("intro");
  if (el && !el.dataset.done) document.getElementById("intro-wait")?.classList.add("show");
}, INTRO_SLOW_MS);

// 전체 화면을 덮는 요소라 어떤 경우에도 갇히면 안 된다
window.setTimeout(dismissIntro, 12000);

function isInAppBrowser() {
  const ua = navigator.userAgent || "";
  return /KAKAOTALK|Instagram|FBAN|FBAV|Line\//i.test(ua);
}

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
          ...(window.JustHereAuth?.getToken?.()
            ? { "X-Guest-Token": window.JustHereAuth.getToken() }
            : {}),
          ...(fetchOpts.headers || {}),
        },
        ...fetchOpts,
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 409 && data && data.stale) return data;
      if (!res.ok) throw new Error(typeof data === "string" ? data : JSON.stringify(data));
      return data;
    } catch (err) {
      lastErr = err;
      if (i < retries && !(err && err.stale)) await sleep(1200 * (i + 1));
    }
  }
  throw lastErr;
}

/** 소프트런치 퍼널 이벤트 — 실패해도 UX 방해 없음 */
function isDesignPreview() {
  return (
    !!state.designPreview ||
    String(state.sessionId || "").toLowerCase().startsWith("design")
  );
}

function track(event, props = {}) {
  if (isDesignPreview()) return;
  try {
    const merged = { ...(props || {}) };
    if (state.sessionId && merged.session_id == null) {
      merged.session_id = state.sessionId;
    }
    if (state.mealContext && merged.meal_context == null) {
      merged.meal_context = state.mealContext;
    }
    const body = {
      event,
      uid: state.uid || window.JustHereAuth?.getUid?.() || "",
      device_id: window.JustHereAuth?.getDeviceId?.() || "",
      props: merged,
    };
    const payload = JSON.stringify(body);
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon("/v1/analytics/event", blob);
      return;
    }
    fetch("/v1/analytics/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  } catch (_) {}
}

function useFallbackLocation(reason) {
  state.lat = FALLBACK_LAT;
  state.lng = FALLBACK_LNG;
  state.locationReady = true;
  state.usingFallbackLoc = true;
  if (!state.trackedLocateFallback) {
    state.trackedLocateFallback = true;
    track("locate_fallback", { reason: String(reason || "").slice(0, 80) });
  }
  setLocStatus(
    `${reason} → ${FALLBACK_LABEL}로 시작해요. 위치 줄의 「확인」을 누르면 다시 잡아요.`,
    false
  );
  const startBtn = $("btn-start");
  if (startBtn) startBtn.disabled = false;
}

const SWIPE_HINT_KEY = "jh_swipe_hint_seen";
const SWIPE_HINT_COPY = "카드를 좌우로 밀어도 같아요.";

function swipeHintSeen() {
  try {
    return !!localStorage.getItem(SWIPE_HINT_KEY);
  } catch {
    return false;
  }
}

function markSwipeHintSeen() {
  try {
    localStorage.setItem(SWIPE_HINT_KEY, "1");
  } catch (_) {}
}

/** 피드 하단 한 줄을 안내·진행·실패 메시지로 함께 쓴다 */
function setFeedHint(text, tone = "") {
  const el = $("feed-hint");
  if (!el) return;
  el.classList.toggle("is-error", tone === "error");
  el.classList.toggle("is-busy", tone === "busy");
  if (tone === "error" || tone === "busy") {
    el.textContent = text || "";
    el.classList.remove("hidden");
    return;
  }
  if (text) {
    el.textContent = text;
    el.classList.remove("hidden");
    return;
  }
  if (!swipeHintSeen() && currentCard() && !state.adjustNeeded) {
    el.textContent = SWIPE_HINT_COPY;
    el.classList.remove("hidden");
    return;
  }
  el.textContent = "";
  el.classList.add("hidden");
}

/** 카드 액션 진행 중: 중복 탭 차단 + 무슨 일이 일어나는지 표시 */
function setSwipeBusy(busy, action) {
  const pass = $("btn-nope");
  const go = $("btn-go");
  const undo = $("btn-undo");
  if (undo) undo.disabled = !!busy;
  [pass, go].forEach((btn) => {
    if (btn) btn.disabled = !!busy;
  });
  if (busy) {
    const target = action === "lets_go" ? go : pass;
    if (target) target.dataset.label = target.textContent;
    if (target) target.textContent = "잠시만요…";
    setFeedHint(
      action === "lets_go" ? "가게를 확정하는 중이에요." : "다음 카드를 가져오는 중이에요.",
      "busy"
    );
    return;
  }
  [pass, go].forEach((btn) => {
    if (btn?.dataset.label) {
      btn.textContent = btn.dataset.label;
      delete btn.dataset.label;
    }
  });
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
  el.classList.toggle("err", !ok && /실패|못|권한이 없어/.test(text));
  syncStartState();
}

/** 시작 버튼은 위치가 준비됐을 때만 열린다 */
function syncStartState() {
  const btn = $("btn-start");
  const hint = $("start-hint");
  if (!btn) return;
  const ready = !!state.locationReady;
  // 위치가 없어도 버튼은 살려 둔다 — 누르면 권한을 물어보고 이어서 진행한다
  btn.disabled = false;
  btn.textContent = ready ? "시작하기" : "위치 확인하고 시작";
  if (!hint) return;
  if (!ready) {
    hint.textContent = "위치 권한을 물어본 뒤 근처 가게를 찾아요.";
  } else if (state.savedTaste?.length && !state.forceRetaste) {
    hint.textContent = "저장된 취향으로 바로 매칭해요.";
  } else {
    hint.textContent = "취향을 아직 안 골랐으면 시작할 때 물어볼게요.";
  }
}

function setToggleUI(intent) {
  document.querySelectorAll(".tog").forEach((b) => {
    const on = b.dataset.intent === intent;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
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

function beginReq() {
  state.reqSeq += 1;
  return state.reqSeq;
}

function isCurrentReq(req) {
  return req === state.reqSeq;
}

function sessionActionBody(extra = {}) {
  return {
    session_id: state.sessionId,
    pack_id: state.packId || undefined,
    meal_context: state.mealContext || undefined,
    epoch: state.epoch || undefined,
    ...extra,
  };
}

function newActionId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `a-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function actionIdFor(key) {
  const prev = state.lastAction;
  if (prev && prev.key === key && prev.pending) return prev.id;
  const id = newActionId();
  state.lastAction = { id, key, pending: true };
  return id;
}

function settleAction() {
  if (state.lastAction) state.lastAction.pending = false;
}

function shownKey(sessionId, packId, menuId) {
  return `${sessionId || ""}:${packId || ""}:${menuId || ""}`;
}

function setMealUI(ctx) {
  const next = ctx || state.mealContext || "meal";
  state.mealContext = next;
  document.querySelectorAll(".meal-tog").forEach((b) => {
    const on = b.dataset.meal === next;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  const hint = next === "meal" ? state.mealHint || "" : "";
  ["onboard-meal-reason", "meal-reason"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    if (hint) {
      el.textContent = hint;
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  });
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
  if (!state.trackedLocateOk) {
    state.trackedLocateOk = true;
    track("locate_ok", { accuracy_m: acc });
  }
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
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      useFallbackLocation("이 브라우저는 위치를 지원하지 않아요");
      resolve({ latitude: FALLBACK_LAT, longitude: FALLBACK_LNG });
      return;
    }
    setLocStatus("현재 위치 확인 중…");
    const opts = force ? GEO_OPTS_FORCE : GEO_OPTS;
    let settled = false;
    const finish = (coords) => {
      if (settled) return;
      settled = true;
      resolve(coords);
    };
    // 일부 웹뷰는 timeout 옵션을 무시하고 영구 대기 → 하드 타임아웃
    const hardMs = (opts.timeout || 8000) + 1500;
    const hardTimer = setTimeout(() => {
      if (settled) return;
      if (state.locationReady && state.lat != null) {
        finish({ latitude: state.lat, longitude: state.lng });
        return;
      }
      const reason = isInAppBrowser()
        ? "인앱 브라우저에서 위치가 막혀 있어요"
        : "위치 확인이 너무 오래 걸려요";
      useFallbackLocation(reason);
      finish({ latitude: FALLBACK_LAT, longitude: FALLBACK_LNG });
    }, hardMs);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(hardTimer);
        applyPosition(pos.coords);
        finish(pos.coords);
      },
      (err) => {
        clearTimeout(hardTimer);
        if (state.locationReady && state.lat != null && state.lng != null) {
          console.warn("geo refresh failed, using cached", err);
          finish({ latitude: state.lat, longitude: state.lng });
          return;
        }
        let reason = "위치를 가져오지 못했어요";
        if (err.code === 1) {
          reason = isInAppBrowser()
            ? "카톡/인앱에선 위치 권한이 막히는 경우가 많아요"
            : "위치 권한이 없어요";
        } else if (err.code === 3) {
          reason = "위치 확인 시간이 초과됐어요";
        }
        useFallbackLocation(reason);
        finish({ latitude: FALLBACK_LAT, longitude: FALLBACK_LNG });
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
  try {
    const q = new URLSearchParams();
    if (state.lat != null && state.lng != null) {
      q.set("lat", String(state.lat));
      q.set("lng", String(state.lng));
    }
    const ctx = await api(`/v1/context?${q}`);
    state.weather = ctx.weather || state.weather || "clear";
    state.intent = ctx.suggested_intent || state.intent;
    state.intentReason = ctx.reason || "";
    state.mealHint = ctx.meal_reason || "";
    setToggleUI(state.intent);
    setMealUI(state.mealContext);
    const ws = $("weather-status");
    if (ws) {
      const label = {
        clear: "맑음",
        rain: "비",
        snow: "눈",
        hot: "더움",
        cold: "추움",
      }[state.weather] || state.weather;
      const temp =
        ctx.weather_meta?.temp_c != null
          ? ` · ${Math.round(ctx.weather_meta.temp_c)}°C`
          : "";
      ws.textContent = `지금 날씨 ${label}${temp} · ${
        state.intent === "delivery" ? "배달" : "방문"
      } 추천`;
    }
  } catch (err) {
    console.warn("smart intent skipped", err);
    state.intentReason = "";
    state.mealHint = "";
    setToggleUI(state.intent);
    setMealUI(state.mealContext);
    const ws = $("weather-status");
    if (ws) ws.textContent = "날씨 확인 실패 — 맑음 기준으로 진행";
  }
}

const TASTE_CATEGORIES = [
  { key: "korean", label: "한식" },
  { key: "chinese", label: "중식" },
  { key: "japanese", label: "일식" },
  { key: "western", label: "양식" },
  { key: "snack", label: "분식" },
  { key: "meat", label: "고기" },
  { key: "asian", label: "아시안" },
  { key: "mexican", label: "멕시칸" },
];

const TASTE_CAT_MIN = 1;
const TASTE_CAT_MAX = 3;

function closeTasteFlow() {
  $("taste-stage")?.classList.add("hidden");
  $("onboard-main")?.classList.remove("hidden");
  $("onboard-cta")?.classList.remove("hidden");
}

function openTasteFlow() {
  $("onboard-main")?.classList.add("hidden");
  $("onboard-cta")?.classList.add("hidden");
  $("taste-stage").classList.remove("hidden");
  $("taste-step-cat").classList.remove("hidden");
  $("taste-step-tone").classList.add("hidden");
  state.tasteIndex = 0;
  state.tasteChoices = [];
  state.forceRetaste = false;
  renderTasteCategories();
  try {
    $("taste-stage").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (_) {}
  applySmartIntent();
}

/** 취향 고르기에서 온보딩으로 돌아가기 (막다른 길 방지) */
function closeTasteFlow() {
  $("taste-stage")?.classList.add("hidden");
  $("onboard-main")?.classList.remove("hidden");
  $("onboard-cta")?.classList.remove("hidden");
  setTasteStatus("");
  state.tasteChoices = [];
  updateTasteReuseHint();
  window.scrollTo(0, 0);
}

function backToTasteCategories() {
  setTasteStatus("");
  $("taste-step-tone")?.classList.add("hidden");
  $("taste-step-cat")?.classList.remove("hidden");
  state.tasteChoices = state.tasteChoices.filter((k) =>
    TASTE_CATEGORIES.some((c) => c.key === k)
  );
  renderTasteCategories();
}

function renderTasteCategories() {
  const box = $("taste-cats");
  if (!box) return;
  box.innerHTML = "";
  const selected = new Set(
    state.tasteChoices.filter((k) => TASTE_CATEGORIES.some((c) => c.key === k))
  );
  TASTE_CATEGORIES.forEach((c) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "taste-cat";
    btn.dataset.key = c.key;
    btn.setAttribute("aria-pressed", selected.has(c.key) ? "true" : "false");
    btn.innerHTML = `<span class="taste-cat-name">${c.label}</span>`;
    btn.onclick = () => toggleTasteCategory(c.key);
    box.appendChild(btn);
  });
  syncTasteCatUI();
}

function toggleTasteCategory(key) {
  const cats = state.tasteChoices.filter((k) =>
    TASTE_CATEGORIES.some((c) => c.key === k)
  );
  const i = cats.indexOf(key);
  if (i >= 0) cats.splice(i, 1);
  else if (cats.length < TASTE_CAT_MAX) cats.push(key);
  state.tasteChoices = cats;
  try {
    if (navigator.vibrate) navigator.vibrate(8);
  } catch (_) {}
  // 전체를 다시 그리면 누른 버튼의 포커스가 사라진다 — 상태만 갱신
  syncTasteCatUI();
}

function syncTasteCatUI() {
  const selected = new Set(
    state.tasteChoices.filter((k) =>
      TASTE_CATEGORIES.some((c) => c.key === k)
    )
  );
  const full = selected.size >= TASTE_CAT_MAX;
  document.querySelectorAll(".taste-cat").forEach((btn) => {
    const on = selected.has(btn.dataset.key);
    btn.classList.toggle("on", on);
    btn.classList.toggle("is-capped", full && !on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  syncTasteCatNext();
}

function syncTasteCatNext() {
  const cats = state.tasteChoices.filter((k) =>
    TASTE_CATEGORIES.some((c) => c.key === k)
  );
  const n = cats.length;
  const hint = $("taste-cat-hint");
  if (hint) {
    // 안내는 문구 줄이 맡고, 버튼은 행동만 말한다
    if (n < TASTE_CAT_MIN) {
      hint.textContent = `${n} / ${TASTE_CAT_MAX} · ${TASTE_CAT_MIN}개부터 넘어갈 수 있어요`;
    } else if (n >= TASTE_CAT_MAX) {
      hint.textContent = `${n} / ${TASTE_CAT_MAX} · 바꾸려면 고른 걸 다시 누르세요`;
    } else {
      hint.textContent = `${n} / ${TASTE_CAT_MAX}`;
    }
  }
  const next = $("btn-taste-next");
  if (!next) return;
  next.disabled = n < TASTE_CAT_MIN;
  next.classList.toggle("ready", n >= TASTE_CAT_MIN);
  next.textContent = "다음";
}

function goTasteToneStep() {
  const cats = state.tasteChoices.filter((k) =>
    TASTE_CATEGORIES.some((c) => c.key === k)
  );
  if (cats.length < TASTE_CAT_MIN) return;
  state.tasteChoices = cats;
  $("taste-step-cat").classList.add("hidden");
  $("taste-step-tone").classList.remove("hidden");
}

async function finishTasteWithTone(tone) {
  const cats = state.tasteChoices.filter((k) =>
    TASTE_CATEGORIES.some((c) => c.key === k)
  );
  state.tasteChoices = tone ? [...cats, tone] : [...cats];
  document.querySelectorAll(".taste-tone").forEach((btn) => {
    btn.classList.toggle("is-on", !!tone && btn.dataset.tone === tone);
  });
  track("taste_done", { taste: [...state.tasteChoices], tone: tone || "skip" });
  setTasteBusy(true);
  try {
    await startSession();
  } catch (err) {
    console.error(err);
    setTasteStatus(
      "근처 가게를 불러오지 못했어요. 잠시 후 다시 눌러 주세요.",
      "error"
    );
  } finally {
    setTasteBusy(false);
  }
}

function setTasteStatus(text, tone = "") {
  const el = $("taste-status");
  if (!el) return;
  el.textContent = text || "";
  el.classList.toggle("hidden", !text);
  el.classList.toggle("is-error", tone === "error");
}

function setTasteBusy(busy) {
  document
    .querySelectorAll(
      ".taste-tone, #btn-taste-skip-tone, #btn-taste-back, #btn-taste-skip, #btn-taste-next, #btn-taste-cancel"
    )
    .forEach((btn) => {
      btn.disabled = !!busy;
    });
  setTasteStatus(busy ? "근처 가게를 찾는 중이에요. 몇 초 걸릴 수 있어요." : "");
}

async function onStartClick() {
  const btn = $("btn-start");
  try {
    btn.disabled = true;
    btn.textContent = "불러오는 중…";

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

    // 저장된 취향이 있으면 스킵 (다시 고르기만 예외)
    const reuse =
      !state.forceRetaste &&
      (state.savedTaste?.length >= 1 || state.tasteChoices?.length >= 1);
    if (reuse) {
      if (!state.tasteChoices?.length) {
        state.tasteChoices = [...state.savedTaste];
      }
      // 세션이 열릴 때까지 버튼을 잠가 둔다 (중복 탭으로 세션이 두 번 생김)
      btn.textContent = "가게 찾는 중…";
      await startSession();
      btn.disabled = false;
      btn.textContent = "시작하기";
      return;
    }

    btn.disabled = false;
    btn.textContent = "시작하기";
    openTasteFlow();
  } catch (err) {
    console.error(err);
    btn.disabled = false;
    btn.textContent = "다시 시도";
    const hint = $("start-hint");
    if (hint) {
      hint.textContent = !state.locationReady
        ? "위치를 아직 못 잡았어요. 위 「확인」을 다시 눌러 주세요."
        : "가게를 불러오지 못했어요. 잠시 후 다시 눌러 주세요.";
    }
  }
}

async function locateAndSyncWeather(force = true) {
  const btn = $("btn-locate");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.textContent = "확인 중";
  }
  if (isInAppBrowser()) {
    setLocStatus(
      "카톡 안에서는 위치가 막힐 수 있어요. 오른쪽 위 메뉴 → 다른 브라우저로 열기."
    );
  } else {
    setLocStatus("현재 위치를 확인하는 중…");
  }
  try {
    await requestLocation(force);
    if (state.usingFallbackLoc) {
      setLocStatus(
        isInAppBrowser()
          ? "인앱에서는 위치를 못 받아 송도 기준이에요. 다른 브라우저로 열면 현재 위치가 잡혀요."
          : "위치 권한이 없어 송도 기준으로 맞춰 뒀어요. 주소창 왼쪽에서 위치를 허용해 주세요.",
        false
      );
    } else {
      setLocStatus(
        `현재 위치 · ${state.lat.toFixed(4)}, ${state.lng.toFixed(4)}`,
        true
      );
    }
    await applySmartIntent();
    if (!state.usingFallbackLoc) startWatchingLocation();
  } catch (err) {
    console.error(err);
    useFallbackLocation("위치를 가져오지 못했어요");
    await applySmartIntent().catch(() => {});
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.textContent = state.locationReady ? "다시" : "확인";
    }
    syncStartState();
  }
}

function setAuthStatus(text) {
  const el = $("auth-status");
  if (!el) return;
  el.textContent = text || "";
  el.classList.toggle("hidden", !text);
}

function updateKakaoLinkButton() {
  const btn = $("btn-kakao-link");
  if (!btn) return;
  btn.classList.remove("hidden");
  btn.innerHTML = kakaoLinkLabel(false);
  if (window.JustHereAuth?.isLinked()) {
    setAuthStatus("도감 저장됨 · 카톡으로 자랑해 보세요");
  }
}

function ensureKakaoSdk() {
  const key = state.meta?.kakao_js_key;
  if (!key) return { ok: false, reason: "no_key" };
  if (!window.Kakao) return { ok: false, reason: "no_sdk" };
  if (!window.Kakao.isInitialized?.()) {
    window.Kakao.init(key);
  }
  if (!window.Kakao.Auth?.authorize) return { ok: false, reason: "no_authorize" };
  return { ok: true };
}

function kakaoRedirectUri() {
  // 카카오 콘솔 Redirect URI와 문자 단위로 일치해야 함 (끝 / 없이 origin)
  return window.location.origin;
}

function showKakaoOverlay(step, msg, { showOk = false } = {}) {
  const overlay = $("kakao-link-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  [1, 2, 3].forEach((n) => {
    const el = $(`kakao-step-${n}`);
    if (!el) return;
    el.classList.remove("on", "done");
    if (n < step) el.classList.add("done");
    if (n === step) el.classList.add("on");
  });
  const m = $("kakao-link-msg");
  if (m) m.textContent = msg || "";
  const ok = $("btn-kakao-overlay-ok");
  if (ok) ok.classList.toggle("hidden", !showOk);
}

function hideKakaoOverlay() {
  const overlay = $("kakao-link-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function saveKakaoResume() {
  const payload = JSON.stringify({
    done: state.lastDone,
    lastReceipt: state.lastReceipt,
    tasteChoices: state.tasteChoices,
    sessionId: state.sessionId,
    lat: state.lat,
    lng: state.lng,
    intent: state.intent,
    mealContext: state.mealContext,
    weather: state.weather,
    locationReady: state.locationReady,
    redirectUri: kakaoRedirectUri(),
  });
  try {
    sessionStorage.setItem("jh_kakao_resume", payload);
    localStorage.setItem("jh_kakao_resume", payload);
    sessionStorage.setItem("jh_kakao_redirect", kakaoRedirectUri());
    localStorage.setItem("jh_kakao_redirect", kakaoRedirectUri());
  } catch (_) {}
}

function consumeKakaoResume() {
  try {
    const raw =
      sessionStorage.getItem("jh_kakao_resume") ||
      localStorage.getItem("jh_kakao_resume");
    sessionStorage.removeItem("jh_kakao_resume");
    localStorage.removeItem("jh_kakao_resume");
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function getSavedKakaoRedirect() {
  return (
    sessionStorage.getItem("jh_kakao_redirect") ||
    localStorage.getItem("jh_kakao_redirect") ||
    kakaoRedirectUri()
  );
}

function clearKakaoRedirect() {
  sessionStorage.removeItem("jh_kakao_redirect");
  localStorage.removeItem("jh_kakao_redirect");
}

function restoreFromResume(resume) {
  if (!resume) return false;
  if (resume.tasteChoices) state.tasteChoices = resume.tasteChoices;
  if (resume.sessionId) state.sessionId = resume.sessionId;
  if (resume.lat != null) state.lat = resume.lat;
  if (resume.lng != null) state.lng = resume.lng;
  if (resume.intent) state.intent = resume.intent;
  if (resume.mealContext) state.mealContext = resume.mealContext;
  if (resume.weather) state.weather = resume.weather;
  if (resume.locationReady) state.locationReady = true;
  if (resume.lastReceipt) state.lastReceipt = resume.lastReceipt;
  if (resume.done) {
    state.lastDone = resume.done;
    showDone(resume.done);
    return true;
  }
  return false;
}

async function completeKakaoCodeLink(code) {
  showKakaoOverlay(2, "카카오 계정을 도감에 연결하는 중이에요…");
  const redirectUri = getSavedKakaoRedirect();
  try {
    const linked = await window.JustHereAuth.linkKakaoCode(api, code, redirectUri);
    state.uid = linked.uid;
    state.authType = "kakao";
    track("kakao_link", {});
    clearKakaoRedirect();
    const resume = consumeKakaoResume();
    const restored = restoreFromResume(resume);
    showKakaoOverlay(
      3,
      restored
        ? "저장 완료! 영수증 화면으로 돌아갈게요."
        : "저장 완료! 다음에 앱을 열면 카카오 계정으로 이어져요.",
      { showOk: true }
    );
    setAuthStatus("카카오 연동 완료! 칭호 도감이 안전하게 저장됐어요.");
    updateKakaoLinkButton();
    const clean = new URL(window.location.href);
    clean.searchParams.delete("code");
    clean.searchParams.delete("state");
    clean.searchParams.delete("error");
    clean.searchParams.delete("error_description");
    window.history.replaceState({}, "", clean.pathname + clean.search + clean.hash);

    const finish = async () => {
      hideKakaoOverlay();
      if (!restored) {
        show("screen-onboard");
        closeTasteFlow();
        updateTasteReuseHint();
        const hint = $("start-hint");
        if (hint) {
          hint.textContent = "카카오 계정에 저장했어요. 저장된 취향으로 바로 시작할 수 있어요.";
        }
      }
      updateKakaoLinkButton();
      refreshTitleBadge();
      // 저장·공유 한 버튼 플로우: 연동 후 카톡 공유까지
      let shareAfter = false;
      try {
        shareAfter = localStorage.getItem("jh_kakao_share_after") === "1";
        localStorage.removeItem("jh_kakao_share_after");
      } catch (_) {}
      if (shareAfter && restored) {
        setTimeout(() => shareToKakaoTalk().catch(console.error), 400);
      }
    };
    const ok = $("btn-kakao-overlay-ok");
    if (ok) {
      ok.onclick = () => finish();
      if (restored) {
        setTimeout(() => finish(), 900);
      }
    } else {
      await finish();
    }
    return linked;
  } catch (err) {
    console.error(err);
    const raw = String(err?.message || err || "");
    let tip = "연결에 실패했어요. 다시 「카카오로 도감 저장」을 눌러 주세요.";
    if (raw.includes("client_secret") || raw.includes("KOE010")) {
      tip =
        "카카오 REST 키 Client Secret 설정이 필요해요. 콘솔에서 Secret 코드를 복사해 Render의 KAKAO_CLIENT_SECRET에 넣거나, Secret을 OFF 하세요.";
    } else if (raw.includes("redirect") || raw.includes("KOE303") || raw.includes("KOE006")) {
      tip =
        "Redirect URI가 달라요. 카카오 콘솔 JavaScript 키에 https://www.justthis.co.kr 와 https://justthis.co.kr 를 등록해 주세요.";
    } else if (raw.includes("missing_rest_key")) {
      tip = "서버에 KAKAO_REST_API_KEY가 없습니다. Render 환경변수를 확인해 주세요.";
    }
    showKakaoOverlay(2, tip, { showOk: true });
    const ok = $("btn-kakao-overlay-ok");
    if (ok) ok.onclick = () => hideKakaoOverlay();
    setAuthStatus("카카오 연동 실패. 다시 시도해 주세요.");
    throw err;
  }
}

function kakaoLinkLabel(busy = false) {
  if (busy) {
    return `<span class="kakao-ico" aria-hidden="true"></span><span id="kakao-link-label">연결 중…</span>`;
  }
  const linked = window.JustHereAuth?.isLinked?.();
  const text = linked ? "카카오톡으로 공유" : "카카오로 저장·공유";
  return `<span class="kakao-ico" aria-hidden="true"></span><span id="kakao-link-label">${text}</span>`;
}

function setKakaoLinkBusy(busy) {
  const btn = $("btn-kakao-link");
  if (!btn) return;
  btn.disabled = !!busy;
  btn.innerHTML = kakaoLinkLabel(busy);
}

async function refreshTitleBadge() {
  const el = $("title-badge");
  if (!el || !state.uid) return;
  try {
    const me = await api(`/v1/me?uid=${encodeURIComponent(state.uid)}`);
    const titles = me.user?.earned_titles || [];
    if (!titles.length) {
      el.classList.add("hidden");
      return;
    }
    const latest = titles.slice(-3).reverse().join(" · ");
    el.textContent = `도감 ${titles.length}개 · ${latest}`;
    el.classList.remove("hidden");
  } catch (_) {
    el.classList.add("hidden");
  }
}

async function shareToKakaoTalk() {
  const sdk = ensureKakaoSdk();
  if (!sdk.ok) {
    alert("카카오 SDK를 불러오지 못했어요. 새로고침 후 다시 시도해 주세요.");
    return;
  }
  if (!window.Kakao?.Share?.sendDefault) {
    alert("카카오톡 공유를 이 환경에서 열 수 없어요. 「링크로 공유」를 사용해 주세요.");
    return;
  }
  if (state.lastDone) {
    try {
      await ensureReceipt(state.lastDone);
    } catch (_) {}
  }
  const receipt = state.lastReceipt || {};
  const url = receipt.share_url || `${location.origin}/`;
  const title = receipt.title || state.lastDone?.receipt_title || "그냥여기 영수증";
  const place = receipt.place_name || state.lastDone?.place_name || "";
  const menu = receipt.menu_name || state.lastDone?.menu_name || "";
  const description = [place, menu].filter(Boolean).join(" · ") || "오늘 점심은 그냥여기";
  // 카톡 피드 썸네일: 앱 아이콘보다 음식 컷이 눌린다
  const imageUrl = `${location.origin}/static/brand/og-home.png`;
  window.Kakao.Share.sendDefault({
    objectType: "feed",
    content: {
      title,
      description,
      imageUrl,
      link: { mobileWebUrl: url, webUrl: url },
    },
    buttons: [
      {
        title: "영수증 보기",
        link: { mobileWebUrl: url, webUrl: url },
      },
    ],
  });
  track("kakao_share", {});
  track("share", { channel: "kakao" });
  setShareStatus("카톡 공유창을 열었어요");
}

async function onKakaoCta() {
  if (window.JustHereAuth?.isLinked()) {
    await shareToKakaoTalk();
    return;
  }
  try {
    localStorage.setItem("jh_kakao_share_after", "1");
  } catch (_) {}
  await linkKakaoAccount();
}

async function linkKakaoAccount() {
  try {
    setKakaoLinkBusy(true);
    const sdk = ensureKakaoSdk();
    if (!sdk.ok) {
      if (sdk.reason === "no_key") {
        alert("서버에 카카오 JS 키가 아직 없습니다. Render Environment에 KAKAO_JS_KEY를 넣어 주세요.");
      } else {
        alert("카카오 SDK를 불러오지 못했어요. 네트워크를 확인한 뒤 새로고침해 주세요.");
      }
      setAuthStatus("게스트 식별 유지 중 — 카카오 연동 대기");
      setKakaoLinkBusy(false);
      return;
    }
    saveKakaoResume();
    showKakaoOverlay(1, "카카오 동의 화면으로 이동해요…");
    window.Kakao.Auth.authorize({
      redirectUri: kakaoRedirectUri(),
    });
  } catch (err) {
    console.error(err);
    setAuthStatus("카카오 연동 실패. 잠시 후 다시 시도해 주세요.");
    setKakaoLinkBusy(false);
  }
}

async function init() {
  if (openDesignPreview()) return;
  state.meta = await api("/v1/meta");
  try {
    if (window.JustHereAuth) {
      const guest = await window.JustHereAuth.ensureGuest(api);
      state.uid = guest.uid;
      state.authType = guest.auth_type || "anonymous";
      const taste =
        guest.user?.preferences?.taste ||
        guest.preferences?.taste ||
        [];
      if (Array.isArray(taste) && taste.length) {
        state.savedTaste = taste;
        state.tasteChoices = [...taste];
      }
      applyExcludeFromMe(guest.user);
      state.goldUnlocked = (guest.user?.unlocks || []).includes("story_gold");
      // /v1/me로 한 번 더 동기화
      if (state.uid) {
        try {
          const me = await api(`/v1/me?uid=${encodeURIComponent(state.uid)}`);
          const t = me.user?.preferences?.taste || [];
          if (Array.isArray(t) && t.length) {
            state.savedTaste = t;
            state.tasteChoices = [...t];
          }
          if (me.user?.auth_type) state.authType = me.user.auth_type;
          state.goldUnlocked = (me.user?.unlocks || []).includes("story_gold");
          applyExcludeFromMe(me.user);
        } catch (_) {}
      }
      updateTasteReuseHint();
    }
  } catch (err) {
    console.warn("guest auth skipped", err);
  }
  track("app_open", {
    standalone:
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true,
    in_app: isInAppBrowser(),
  });
  // 카카오 authorize 콜백 (?code=)
  try {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const kakaoErr = params.get("error");
    if (kakaoErr) {
      showKakaoOverlay(1, "카카오 로그인이 취소되었거나 실패했어요.", {
        showOk: true,
      });
      const ok = $("btn-kakao-overlay-ok");
      if (ok) ok.onclick = () => hideKakaoOverlay();
      setAuthStatus("카카오 로그인이 취소되었거나 실패했어요.");
    } else if (code && window.JustHereAuth) {
      showKakaoOverlay(1, "동의 완료. 계정 연결을 이어갈게요…");
      await completeKakaoCodeLink(code);
    }
  } catch (err) {
    console.error(err);
    setAuthStatus("카카오 연동 실패. 다시 시도해 주세요.");
  }
  $("btn-start").onclick = onStartClick;
  syncStartState();
  const retasteBtn = $("btn-retaste");
  if (retasteBtn) {
    retasteBtn.onclick = () => {
      state.forceRetaste = true;
      state.tasteChoices = [];
      openTasteFlow();
    };
  }
  const tasteNext = $("btn-taste-next");
  if (tasteNext) tasteNext.onclick = () => goTasteToneStep();
  const tasteSkip = $("btn-taste-skip");
  if (tasteSkip) {
    tasteSkip.onclick = async () => {
      state.tasteChoices = [];
      track("taste_done", { taste: [], tone: "skip_all" });
      setTasteBusy(true);
      try {
        await startSession();
      } catch (err) {
        console.error(err);
        setTasteStatus("근처 가게를 불러오지 못했어요. 잠시 후 다시 눌러 주세요.", "error");
      } finally {
        setTasteBusy(false);
      }
    };
  }
  document.querySelectorAll(".taste-tone").forEach((btn) => {
    btn.onclick = () => finishTasteWithTone(btn.dataset.tone || "");
  });
  const skipTone = $("btn-taste-skip-tone");
  if (skipTone) skipTone.onclick = () => finishTasteWithTone("");
  const tasteCancel = $("btn-taste-cancel");
  if (tasteCancel) tasteCancel.onclick = () => closeTasteFlow();
  const tasteBack = $("btn-taste-back");
  if (tasteBack) tasteBack.onclick = () => backToTasteCategories();
  const locateBtn = $("btn-locate");
  if (locateBtn) locateBtn.onclick = () => locateAndSyncWeather(true);
  $("btn-nope").onclick = () => swipe("nope");
  $("btn-go").onclick = () => swipe("lets_go");
  const undoBtn = $("btn-undo");
  if (undoBtn) undoBtn.onclick = () => undoCard();
  document.querySelectorAll(".meal-tog").forEach((btn) => {
    btn.onclick = () => selectMealContext(btn.dataset.meal);
  });
  const mealYes = $("btn-meal-yes");
  if (mealYes) mealYes.onclick = () => submitMeal(true);
  const mealSkip = $("btn-meal-skip");
  if (mealSkip) mealSkip.onclick = () => submitMeal(false);
  $("btn-again").onclick = () => location.reload();
  $("btn-share").onclick = () => shareReceipt();
  const kakaoBtn = $("btn-kakao-link");
  if (kakaoBtn) kakaoBtn.onclick = () => onKakaoCta();
  const duoBtn = $("btn-duo");
  if (duoBtn) duoBtn.onclick = () => createDuoInvite();
  const duoDone = $("btn-duo-done");
  if (duoDone) duoDone.onclick = () => createDuoInvite();
  const storyImgBtn = $("btn-story-image");
  if (storyImgBtn) storyImgBtn.onclick = () => makeStoryImage();
  const storyBtn = $("btn-story-unlock");
  if (storyBtn) storyBtn.onclick = () => unlockStoryGold();
  updateStoryReward();
  const reloadBtn = $("btn-reload-feed");
  if (reloadBtn) {
    reloadBtn.onclick = async () => {
      if (reloadBtn.disabled) return;
      reloadBtn.disabled = true;
      reloadBtn.textContent = "찾는 중…";
      try {
        await ensureFreshLocation();
        const req = beginReq();
        const data = await api("/v1/session", {
          method: "POST",
          body: JSON.stringify({
            lat: state.lat,
            lng: state.lng,
            intent: state.intent,
            weather: state.weather,
            meal_context: state.mealContext,
            taste: state.tasteChoices,
            uid: state.uid || undefined,
          }),
        });
        if (applyFeed(data, { req })) {
          setToggleUI(state.intent);
          renderCard();
        }
      } catch (err) {
        console.error(err);
        const msg = $("empty-msg");
        if (msg) msg.textContent = "다시 불러오지 못했어요. 잠시 후 시도해 주세요.";
      } finally {
        reloadBtn.disabled = false;
        reloadBtn.textContent = "다시 시도";
      }
    };
  }

  const emptySwap = $("btn-empty-intent");
  if (emptySwap) {
    emptySwap.onclick = () => {
      document.querySelector(".tog:not(.on)")?.click();
    };
  }
  const emptyMeal = $("btn-empty-meal");
  if (emptyMeal) {
    emptyMeal.onclick = () => selectMealContext("meal");
  }
  const emptyLocate = $("btn-empty-locate");
  if (emptyLocate) {
    emptyLocate.onclick = async () => {
      if (emptyLocate.disabled) return;
      emptyLocate.disabled = true;
      try {
        await locateAndSyncWeather(true);
        if (state.sessionId) await refreshFeed();
        else await startSession();
        renderCard();
      } catch (err) {
        console.error(err);
        setFeedHint("위치를 다시 확인하지 못했어요.", "error");
      } finally {
        emptyLocate.disabled = false;
      }
    };
  }

  document.querySelectorAll(".tog").forEach((btn) => {
    btn.onclick = async () => {
      if (state.swiping || state.modeSwitching) return;
      const next = btn.dataset.intent;
      if (!next || next === state.intent) return;
      const prev = state.intent;
      const prevReason = state.intentReason;
      state.modeSwitching = true;
      state.intent = next;
      state.intentReason = "";
      setToggleUI(state.intent);
      setFeedHint(
        next === "delivery"
          ? "주문할 브랜드를 고르는 중이에요."
          : "걸어갈 수 있는 곳으로 다시 찾는 중이에요.",
        "busy"
      );
      document.querySelectorAll(".tog").forEach((b) => (b.disabled = true));
      try {
        await refreshFeed();
        renderCard();
      } catch (err) {
        console.error(err);
        state.intent = prev;
        state.intentReason = prevReason;
        setToggleUI(prev);
        setFeedHint(
          `${next === "delivery" ? "배달" : "방문"}으로 못 바꿨어요. 잠시 후 다시 눌러 주세요.`,
          "error"
        );
      } finally {
        state.modeSwitching = false;
        document.querySelectorAll(".tog").forEach((b) => (b.disabled = false));
      }
    };
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("detail")?.classList.contains("hidden")) hideDetailModal();
  });

  setupSwipeGestures();
  setupLongPress();
  setupCardKeys();
  setupInstallPwa();
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

const TASTE_TONE_LABEL = { spicy: "매콤", mild: "담백" };

function tasteLabels(keys) {
  return (keys || [])
    .map(
      (k) =>
        TASTE_CATEGORIES.find((c) => c.key === k)?.label ||
        TASTE_TONE_LABEL[k] ||
        ""
    )
    .filter(Boolean);
}

/** 취향 행 요약 — 저장값이 있으면 그대로 보여주고 「변경」으로 바꾼다 */
function updateTasteReuseHint() {
  const summary = $("taste-summary");
  const retaste = $("btn-retaste");
  const saved = state.savedTaste || [];
  if (summary) {
    const labels = tasteLabels(saved);
    summary.textContent = labels.length
      ? labels.join(" · ")
      : "아직 고르지 않았어요";
  }
  if (retaste) retaste.textContent = saved.length ? "변경" : "고르기";
  renderExcludeRow();
  syncStartState();
}

function excludeLabel(key) {
  return CATEGORY_LABELS[key] || key || "이 종류";
}

function applyExcludeFromMe(user) {
  const raw = user?.preferences?.exclude_categories || [];
  state.excludeCats = [...new Set(raw.map((x) => String(x || "").trim()).filter(Boolean))];
  renderExcludeRow();
}

function renderExcludeRow() {
  const row = $("exclude-row");
  const dd = $("exclude-summary");
  if (!row || !dd) return;
  const keys = state.excludeCats || [];
  if (!keys.length) {
    row.classList.add("hidden");
    dd.textContent = "";
    return;
  }
  row.classList.remove("hidden");
  dd.innerHTML = "";
  keys.forEach((key) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "exclude-chip";
    btn.textContent = `${excludeLabel(key)} 되돌리기`;
    btn.onclick = () => restoreExclude(key);
    dd.appendChild(btn);
  });
}

async function restoreExclude(key) {
  const uid = state.uid || window.JustHereAuth?.getUid?.() || "";
  if (!uid || !key) return;
  try {
    const data = await api("/v1/me/exclude", {
      method: "POST",
      body: JSON.stringify({
        uid,
        kind: key,
        exclude: false,
        session_id: state.sessionId || undefined,
      }),
    });
    state.excludeCats = (state.excludeCats || []).filter((x) => x !== key);
    if (Array.isArray(data.exclude_categories)) {
      state.excludeCats = data.exclude_categories;
    }
    renderExcludeRow();
    if (data.session_id) {
      const req = beginReq();
      if (applyFeed(data, { req })) renderCard();
    }
  } catch (err) {
    console.error(err);
  }
}

async function submitExclude(card) {
  const uid = state.uid || window.JustHereAuth?.getUid?.() || "";
  const kind = String(card?.kind || "").trim();
  const category = String(card?.category || "").trim();
  if (!uid || (!kind && !category)) return;
  const already = (state.excludeCats || []).includes(kind || category);
  try {
    const data = await api("/v1/me/exclude", {
      method: "POST",
      body: JSON.stringify({
        uid,
        session_id: state.sessionId || undefined,
        kind,
        category: kind ? "" : category,
        exclude: !already,
      }),
    });
    track("exclude", {
      kind: kind || category,
      exclude: !already,
      pack_id: card.pack_id || state.packId,
      logic_version: card.logic_version || state.logicVersion,
    });
    if (Array.isArray(data.exclude_categories)) {
      state.excludeCats = data.exclude_categories;
    } else if (!already) {
      state.excludeCats = [...new Set([...(state.excludeCats || []), kind || category])];
    } else {
      state.excludeCats = (state.excludeCats || []).filter((x) => x !== (kind || category));
    }
    renderExcludeRow();
    hideDetailModal();
    if (data.session_id) {
      const req = beginReq();
      if (applyFeed(data, { req })) renderCard();
    }
    const label = excludeLabel(kind || category);
    setFeedHint(
      already ? `${label} 다시 추천에 넣을게요.` : `${label} 빼 두었어요.`,
      already ? "" : "ok"
    );
  } catch (err) {
    console.error(err);
    setFeedHint("종류를 저장하지 못했어요. 다시 눌러 주세요.", "error");
  }
}

async function startSession() {
  await ensureFreshLocation();
  const req = beginReq();
  const data = await api("/v1/session", {
    method: "POST",
    body: JSON.stringify({
      lat: state.lat,
      lng: state.lng,
      intent: state.intent,
      weather: state.weather,
      meal_context: state.mealContext,
      taste: state.tasteChoices,
      uid: state.uid || undefined,
    }),
  });
  track("session_start", {
    intent: state.intent,
    weather: state.weather,
    taste: state.tasteChoices || [],
    fallback_loc: !!state.usingFallbackLoc,
  });
  if (state.tasteChoices?.length) {
    state.savedTaste = [...state.tasteChoices];
    updateTasteReuseHint();
  }
  if (!applyFeed(data, { req })) return;
  show("screen-feed");
  setToggleUI(state.intent);
  setMealUI(state.mealContext);
  renderCard();
}

async function refreshFeed() {
  if (!state.sessionId) return;
  const req = beginReq();
  await ensureFreshLocation();
  const q = new URLSearchParams({
    session_id: state.sessionId,
    intent: state.intent,
    weather: state.weather,
    meal_context: state.mealContext,
    lat: String(state.lat),
    lng: String(state.lng),
  });
  const data = await api(`/v1/feed?${q}`);
  if (!applyFeed(data, { req })) return;
}

async function selectMealContext(next) {
  if (!next || next === state.mealContext) return;
  if (state.swiping || state.modeSwitching) return;
  const prev = state.mealContext;
  state.mealContext = next;
  setMealUI(next);
  if (!state.sessionId) return;
  state.modeSwitching = true;
  document.querySelectorAll(".meal-tog").forEach((b) => {
    b.disabled = true;
  });
  try {
    await refreshFeed();
    renderCard();
  } catch (err) {
    console.error(err);
    state.mealContext = prev;
    setMealUI(prev);
    setFeedHint("상황을 바꾸지 못했어요. 잠시 후 다시 눌러 주세요.", "error");
  } finally {
    state.modeSwitching = false;
    document.querySelectorAll(".meal-tog").forEach((b) => {
      b.disabled = false;
    });
  }
}

function applyFeed(data, opts = {}) {
  if (opts.req != null && !isCurrentReq(opts.req)) return false;
  if (!data || !data.session_id) return false;
  state.sessionId = data.session_id;
  state.cards = data.cards || [];
  state.perfect = data.perfect_slots_left;
  state.radius = data.effective_radius_m;
  state.packId = data.pack_id || "";
  state.packRank = data.pack_rank || 0;
  state.packSize = data.pack_size || 3;
  state.adjustNeeded = !!data.adjust_needed;
  state.canUndo = !!data.can_undo;
  state.adjustOptions = data.adjust_options || [];
  state.logicVersion = data.logic_version || "";
  if (data.epoch != null) state.epoch = data.epoch;
  state.emptyTitle = data.empty_title || "";
  state.emptyCopy = data.empty_copy || "";
  state.emptyActions = data.empty_actions || [];
  if (data.session_id && data.session_id !== state.shownSessionId) {
    state.shownKeys = {};
    state.shownSessionId = data.session_id;
  }
  if (Array.isArray(data.exclude_categories)) {
    state.excludeCats = data.exclude_categories;
    renderExcludeRow();
  }
  if (data.intent) state.intent = data.intent;
  if (data.meal_context) setMealUI(data.meal_context);
  state.inventorySource = data.inventory_source || "";
  const copy = $("feed-copy");
  if (copy) {
    copy.textContent = "";
    copy.classList.add("hidden");
  }
  renderFeedChrome();
  syncUndoBtn();
  const card = currentCard();
  if (card && !opts.fromUndo) {
    const key = shownKey(state.sessionId, card.pack_id || state.packId, card.menu_id);
    if (!state.shownKeys[key]) {
      state.shownKeys[key] = true;
      track("recommend_shown", {
        session_id: state.sessionId,
        pack_id: card.pack_id || state.packId,
        menu_id: card.menu_id,
        candidate_id: card.menu_id,
        verified_menu_id: card.verified_menu_id || "",
        place_id: card.place_id || "",
        menu_name: card.menu_name || "",
        rank: card.pack_rank || state.packRank,
        logic_version: card.logic_version || state.logicVersion,
        intent: state.intent,
      });
    }
  } else if (state.adjustNeeded && !opts.fromUndo) {
    track("pack_exhausted", {
      pack_id: state.packId,
      logic_version: state.logicVersion,
      intent: state.intent,
    });
  }
  return true;
}

function currentCard() {
  return state.cards[0] || null;
}

const SOURCE_LABELS = {
  hub_seed: "송도 큐레이션",
  hub_seed_anchored: "송도 · 내위치",
  "hub+kakao": "주변 실상호",
  kakao: "주변 실상호",
  seed_fallback: "라이트",
  empty: "결과 없음",
  brand: "공식 주문",
};

function progressLabel(rank, size) {
  const n = Number(rank) || 1;
  const s = Number(size) || 3;
  return `추천 ${n}/${s}`;
}

function renderFeedChrome() {
  const progress = $("feed-progress");
  if (progress) {
    progress.textContent = state.adjustNeeded
      ? "다른 메뉴를 찾아볼까요?"
      : progressLabel(state.packRank, state.packSize);
  }
  const radius = $("visit-radius");
  if (radius) {
    const show = state.intent === "visit" && state.radius && !state.adjustNeeded;
    radius.textContent = show ? `· ${state.radius}m 안` : "";
    radius.classList.toggle("hidden", !show);
  }
}

function cardPresentation(card) {
  if (card?.menu_verified && card.menu_name) {
    return {
      type: "menu",
      title: card.menu_name,
      sub: card.place_name || "",
      pass: "다른 메뉴",
      go: "이거 먹을래",
    };
  }
  if (card?.is_brand) {
    return {
      type: "brand",
      title: card.place_name || "",
      sub: card.kind || categoryLabel(card),
      pass: "다른 후보",
      go: "여기로 할게",
    };
  }
  return {
    type: "visit",
    title: card?.place_name || "",
    sub: categoryLabel(card),
    pass: "다른 가게",
    go: "여기로 할게",
  };
}

const EXAMPLE_PHOTO_CAP = "음식 종류 예시";

function photoRole(card) {
  if (card?.photo_role) return card.photo_role;
  if (card?.photo_is_product || card?.photo_is_menu) {
    return card.is_brand ? "product" : "menu";
  }
  if (card?.photo_is_example || card?.photo_kind === "example") return "example";
  const url = String(card?.image_url || "");
  if (/unsplash\.com|picsum\.photos|example-photos/.test(url)) return "example";
  if (card?.is_brand) return url ? "example" : "";
  if (card?.menu_verified && url) return "menu";
  if (card?.has_photo && url) return "store";
  return "";
}

function isExamplePhoto(card, role) {
  if (!card) return false;
  if (card.photo_is_product || card.photo_is_menu) return false;
  if (role === "product" || role === "menu" || role === "store") return false;
  if (card.photo_is_example || role === "example") return true;
  return !!card.is_brand && !!String(card.image_url || "").trim();
}

function usablePhoto(card) {
  if (!card) return null;
  const url = String(card.image_url || "").trim();
  if (!url || url.includes("picsum.photos") || card.has_photo === false) return null;
  const role = photoRole(card);
  const example = isExamplePhoto(card, role);
  if (card.is_brand) {
    if (!role) return null;
    return { url, role, example };
  }
  if (example) return null;
  if (role === "menu" || role === "store") return { url, role, example: false };
  return null;
}

function showExampleCaption(on) {
  const wrap = $("card-media");
  let cap = $("card-photo-cap");
  if (on && wrap && !cap) {
    cap = document.createElement("span");
    cap.id = "card-photo-cap";
    cap.className = "photo-cap";
    wrap.appendChild(cap);
  }
  if (!cap) return;
  if (on) {
    cap.textContent = EXAMPLE_PHOTO_CAP;
    cap.classList.remove("hidden");
    cap.hidden = false;
    cap.setAttribute("data-photo-kind", "example");
  } else {
    cap.classList.add("hidden");
    cap.removeAttribute("data-photo-kind");
  }
}

function formatPrice(krw) {
  const n = Number(krw);
  if (!n) return "";
  if (n < 10000) return `${Math.round(n / 1000)}천원`;
  const man = Math.floor(n / 10000);
  const rest = n % 10000;
  if (rest === 0) return `${man}만원`;
  return `${man}만${Math.round(rest / 1000)}천원`;
}

function priceFact(card) {
  const src = card?.price_source;
  const label = String(card?.price_label || "").trim();
  const menuPretty = formatPrice(card?.price_menu_krw);
  const perPersonPretty = formatPrice(card?.price_per_person_krw);
  if (src === "catchtable_listed" || src === "listed_menu") {
    if (menuPretty) return `${label || "메뉴 가격"} ${menuPretty}`.trim();
    return label || "가격 미확인";
  }
  if (card?.price_unit === "menu" && !card?.portion_confirmed) {
    if (menuPretty) return `${label || "메뉴 가격"} ${menuPretty}`.trim();
    return "가격 미확인";
  }
  const band = String(card?.price_band || "").trim();
  const listed = src === "listed" || src === "confirmed";
  const pretty = band || perPersonPretty || formatPrice(card?.price_krw);
  if (!pretty) return "가격 미확인";
  if (listed) return pretty.replace(/^예상\s*/, "");
  return pretty.startsWith("예상") ? pretty : `예상 ${pretty}`;
}

function displayWhy(card) {
  const raw = String(card?.why || "").trim();
  if (!raw) return "";
  if (
    /확인된 메뉴|공식 주문|주문 페이지|주문 화면|출처|가격은 아직 확인|데이터가 확인/.test(
      raw
    )
  ) {
    return "";
  }
  return raw;
}

function detailChipLabel(card, photo) {
  const bits = [];
  if (photo) bits.push("사진");
  if (!card?.is_brand && card?.address && card.address !== "주소 확인 중") bits.push("주소");
  if (card?.is_brand) bits.push("주문", "가격");
  else bits.push("가게 정보");
  return bits.join("·");
}

/* 실제 사진이 확인된 경우에만 띄운다. 방문 카드에 음식 예시 사진을 붙이지 않는다. */
function setCardPhoto(card) {
  const el = $("card");
  const wrap = $("card-media");
  const img = $("card-photo-img");
  if (!el || !wrap || !img) return;
  el.classList.remove("has-photo");
  wrap.style.backgroundImage = "";
  img.onload = null;
  img.onerror = null;
  img.removeAttribute("src");
  showExampleCaption(false);

  const photo = usablePhoto(card);
  if (!photo) {
    wrap.classList.add("hidden");
    return;
  }
  wrap.classList.remove("hidden");
  img.alt = photo.example ? EXAMPLE_PHOTO_CAP : cardPresentation(card).title;
  img.style.objectPosition = card.photo_focus || "50% 40%";
  showExampleCaption(!!photo.example);
  const token = card.card_id;
  img.onload = () => {
    if (currentCard()?.card_id !== token) return;
    el.classList.add("has-photo");
  };
  img.onerror = () => {
    if (currentCard()?.card_id !== token) return;
    wrap.classList.add("hidden");
    el.classList.remove("has-photo");
    img.removeAttribute("src");
    showExampleCaption(false);
    const chip = $("btn-card-detail");
    if (chip) chip.textContent = detailChipLabel(card, null);
  };
  img.src = photo.url;
  const next = usablePhoto(state.cards[1]);
  if (next) {
    const pre = new Image();
    pre.src = next.url;
  }
}

function distanceLabel(m) {
  if (m == null) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`;
}

function walkMinutes(m) {
  if (m == null) return null;
  return Math.max(1, Math.round(m / 80));
}

const CATEGORY_LABELS = {
  korean: "한식",
  chinese: "중식",
  japanese: "일식",
  western: "양식",
  snack: "분식",
  meat: "고기",
  asian: "아시안",
  mexican: "멕시칸",
  cafe: "카페",
  noodle: "면",
};

function categoryLabel(card) {
  if (card?.is_brand) {
    return card.kind || CATEGORY_LABELS[card.category] || "근처 가게";
  }
  return CATEGORY_LABELS[card?.category] || card?.menu_name || "식당";
}

function kindLabel(card) {
  if (card?.is_brand) {
    const menu = String(card.menu_name || "").trim();
    if (menu && menu !== "추천 메뉴") return menu;
    return categoryLabel(card);
  }
  if (card?.menu_verified && card.menu_name) return card.menu_name;
  const cat = CATEGORY_LABELS[card?.category] || card?.menu_name || "식당";
  const text = String(cat).trim();
  if (!text) return "추정 식당";
  return text.startsWith("추정 ") ? text : `추정 ${text}`;
}

function displayMenuName(data) {
  const name = String(data?.menu_name || "").trim();
  const delivery =
    data?.is_brand ||
    data?.handoff?.intent === "delivery" ||
    data?.menu_source === "typical";
  if (delivery || data?.menu_verified) return name;
  if (!name) return "추정 식당";
  return name.startsWith("추정 ") ? name : `추정 ${name}`;
}

/* 히어로는 한 줄에 들어가야 크게 읽힌다 — "1.5~2.5만원"은 넘치므로 짧게 만든다 */
function shortPrice(krw) {
  const n = Number(krw);
  if (!n) return "—";
  if (n < 10000) return `${Math.round(n / 1000)}천원`;
  const man = n / 10000;
  return n % 10000 === 0 ? `${man}만원대` : `${man.toFixed(1)}만원`;
}

/* 카드에서 가장 크게 보여줄 값.
   방문은 도착까지 걸리는 시간, 배달은 지점이 없어 시간을 알 수 없으니 예산. */
function heroMetric(card) {
  if (card.is_brand) {
    return { num: shortPrice(card.price_krw), cap: "예상 1인" };
  }
  const mins = walkMinutes(card.distance_m);
  if (mins == null) return { num: "—", cap: "걸어가면 도착" };
  return { num: `${mins}분`, cap: "걸어가면 도착" };
}

/** 서버 해시태그(#스트레스_풀리는_국물)를 읽기 쉬운 문장으로 */
function readableTag(raw) {
  return String(raw || "")
    .replace(/^#/, "")
    .replace(/_/g, " ")
    .trim();
}

function renderCard() {
  const card = currentCard();
  const empty = $("empty");
  const el = $("card");
  const adjust = $("adjust-sheet");
  const actions = document.querySelector(".bottom.actions");

  if (state.adjustNeeded) {
    el.classList.add("hidden");
    empty.classList.add("hidden");
    $("feed-hint")?.classList.add("hidden");
    if (actions) actions.classList.add("hidden");
    $("screen-feed")?.classList.add("is-adjust");
    $("screen-feed")?.classList.remove("is-nophoto");
    renderAdjustSheet();
    syncUndoBtn();
    return;
  }
  if (adjust) adjust.classList.add("hidden");

  if (!card) {
    el.classList.add("hidden");
    empty.classList.remove("hidden");
    if (actions) actions.classList.add("hidden");
    const title = $("empty")?.querySelector(".empty-title");
    if (title) title.textContent = state.emptyTitle || "지금 보여줄 곳이 없어요";
    const msg = $("empty-msg");
    if (msg) {
      msg.textContent = state.usingFallbackLoc
        ? "임시 위치라서 근처 가게를 못 찾았어요. 위치 권한을 허용하면 결과가 달라져요."
        : state.emptyCopy ||
          "이 위치에서 조건에 맞는 가게를 못 찾았어요. 위치를 바꾸거나 다시 시도해 주세요.";
    }
    const swapBtn = $("btn-empty-intent");
    if (swapBtn) {
      swapBtn.textContent =
        state.intent === "delivery" ? "방문으로 바꿔 보기" : "배달로 바꿔 보기";
      swapBtn.classList.remove("hidden");
    }
    const mealBtn = $("btn-empty-meal");
    if (mealBtn) {
      const showMeal = state.mealContext && state.mealContext !== "meal";
      mealBtn.classList.toggle("hidden", !showMeal);
    }
    const locBtn = $("btn-empty-locate");
    if (locBtn) locBtn.classList.remove("hidden");
    $("feed-hint")?.classList.add("hidden");
    $("screen-feed")?.classList.remove("is-nophoto", "is-adjust");
    syncUndoBtn();
    return;
  }
  setFeedHint("");
  empty.classList.add("hidden");
  if (actions) actions.classList.remove("hidden");
  el.classList.remove("hidden");
  el.classList.remove("gold");
  $("gold-badge")?.classList.add("hidden");
  const view = cardPresentation(card);
  const photo = usablePhoto(card);
  setCardPhoto(card);
  $("card-title").textContent = view.title;
  $("card-sub").textContent = view.sub;
  $("card-place").textContent = card.place_name || "";
  $("card-menu").textContent = view.sub;
  const where = $("card-where");
  if (where) {
    where.textContent = "";
    where.classList.add("hidden");
  }
  const pass = $("btn-nope");
  const go = $("btn-go");
  if (pass) pass.textContent = view.pass;
  if (go) go.textContent = view.go;

  const fact2 = $("card-fact2-key")?.parentElement;
  if (view.type === "brand") {
    $("card-fact1-key").textContent = "가격";
    $("card-fact1-val").textContent = priceFact(card);
    if (fact2) fact2.classList.add("hidden");
  } else {
    if (fact2) fact2.classList.remove("hidden");
    const mins = walkMinutes(card.distance_m);
    const walk =
      mins != null
        ? `도보 약 ${mins}분`
        : String(card.eta_label || "").replace(/^도보\s+(?!약)/, "도보 약 ");
    $("card-fact1-key").textContent = "거리";
    $("card-fact1-val").textContent = walk
      ? `${distanceLabel(card.distance_m)} · ${walk}`
      : distanceLabel(card.distance_m);
    $("card-fact2-key").textContent = "가격";
    $("card-fact2-val").textContent = priceFact(card);
  }
  const chip = $("btn-card-detail");
  if (chip) chip.textContent = detailChipLabel(card, photo);

  const note = $("card-note");
  const noteText = displayWhy(card);
  note.textContent = noteText;
  note.classList.toggle("hidden", !noteText);
  const feed = $("screen-feed");
  if (feed) {
    feed.classList.toggle("is-nophoto", !photo);
    feed.classList.toggle("is-adjust", false);
  }

  const tagEl = $("card-tag");
  const deal = card.deal;
  if (deal && deal.title) {
    const bits = [];
    if (deal.audience && deal.audience !== "everyone" && deal.audience_label) {
      bits.push(deal.audience_label);
    }
    bits.push(deal.title, deal.condition);
    tagEl.textContent = bits.filter(Boolean).join(" · ");
    tagEl.classList.remove("hidden");
  } else {
    tagEl.textContent = "";
    tagEl.classList.add("hidden");
  }
  $("detail").classList.add("hidden");
  el.style.transform = "";
  el.style.opacity = "1";
  syncUndoBtn();
}

function renderAdjustSheet() {
  const sheet = $("adjust-sheet");
  const box = $("adjust-options");
  if (!sheet || !box) return;
  box.innerHTML = "";
  const opts = state.adjustOptions || [];
  opts
    .filter((opt) => opt.id !== "again")
    .forEach((opt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost adjust-opt";
      btn.dataset.option = opt.id;
      btn.textContent = opt.label;
      btn.onclick = () => submitAdjust(opt.id);
      box.appendChild(btn);
    });
  const again = $("btn-adjust-again");
  const againOpt = opts.find((opt) => opt.id === "again");
  if (again) {
    again.textContent = againOpt?.label || "조건 그대로 다시";
    again.classList.toggle("hidden", !againOpt);
    again.onclick = againOpt ? () => submitAdjust("again") : null;
  }
  sheet.classList.remove("hidden");
}

function syncUndoBtn() {
  const btn = $("btn-undo");
  if (!btn) return;
  const show = !!state.canUndo && !state.swiping;
  btn.classList.toggle("hidden", !show);
  const host = state.adjustNeeded ? $("adjust-undo-slot") : $("feed-undo-slot");
  if (host && btn.parentElement !== host) host.appendChild(btn);
}

async function submitAdjust(option) {
  if (isDesignPreview() || !state.sessionId || state.swiping) return;
  const req = beginReq();
  const actionId = actionIdFor(`adjust:${option}:${state.packId}`);
  state.swiping = true;
  try {
    const data = await api("/v1/adjust", {
      method: "POST",
      body: JSON.stringify(sessionActionBody({ option, action_id: actionId })),
    });
    if (data.stale) {
      settleAction();
      if (applyFeed(data, { req })) renderCard();
      return;
    }
    settleAction();
    track("adjust", {
      option,
      pack_id: state.packId,
      logic_version: data.logic_version || state.logicVersion,
    });
    if (applyFeed(data, { req })) renderCard();
  } catch (err) {
    console.error(err);
    setFeedHint("조건을 바꾸지 못했어요. 다시 눌러 주세요.", "error");
  } finally {
    state.swiping = false;
    syncUndoBtn();
  }
}

async function undoCard() {
  if (isDesignPreview()) return;
  if (!state.sessionId || !state.canUndo || state.swiping) return;
  const req = beginReq();
  const actionId = actionIdFor(`undo:${state.packId}:${state.packRank}`);
  state.swiping = true;
  try {
    const data = await api("/v1/undo", {
      method: "POST",
      body: JSON.stringify(
        sessionActionBody({ uid: state.uid || undefined, action_id: actionId })
      ),
    });
    if (data.stale) {
      settleAction();
      if (applyFeed(data, { req })) renderCard();
      return;
    }
    settleAction();
    const shown = (data.cards && data.cards[0]) || {};
    track("undo", {
      pack_id: data.pack_id || state.packId,
      menu_id: shown.menu_id || "",
      candidate_id: shown.menu_id || "",
      replay: true,
      logic_version: data.logic_version || state.logicVersion,
    });
    if (applyFeed(data, { req, fromUndo: true })) renderCard();
  } catch (err) {
    console.error(err);
    setFeedHint("이전 후보를 불러오지 못했어요.", "error");
  } finally {
    state.swiping = false;
    syncUndoBtn();
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
  $("match-sub").textContent = `${data.place_name} · ${displayMenuName(data)}`;
  flash.classList.remove("hidden");

  window.setTimeout(() => {
    flash.classList.add("hidden");
    showDone(data);
  }, 700);
}

/** @returns {Promise<boolean>} 카드가 실제로 넘어갔는지 */
async function swipe(action) {
  const card = currentCard();
  if (isDesignPreview() || !card || state.swiping) return false;
  const req = beginReq();
  const actionId = actionIdFor(`swipe:${action}:${card.menu_id}:${card.pack_id || state.packId}`);
  state.swiping = true;
  setSwipeBusy(true, action);
  try {
    const data = await api("/v1/swipe", {
      method: "POST",
      body: JSON.stringify(
        sessionActionBody({
          card_id: card.card_id,
          menu_id: card.menu_id,
          action,
          action_id: actionId,
          uid: state.uid || undefined,
        })
      ),
    });
    if (data.stale) {
      settleAction();
      if (applyFeed(data, { req })) renderCard();
      return false;
    }
    settleAction();
    markSwipeHintSeen();
    if (action === "lets_go") {
      track("swipe_go", {
        category: card.category || "",
        pack_id: card.pack_id || state.packId,
        menu_id: card.menu_id,
        verified_menu_id: card.verified_menu_id || "",
        place_id: card.place_id || "",
        rank: card.pack_rank || state.packRank,
        logic_version: card.logic_version || state.logicVersion,
      });
      track("match_done", {
        category: card.category || "",
        intent: state.intent,
        persona: data.persona?.id || "",
        pack_id: card.pack_id || state.packId,
        menu_id: card.menu_id,
        verified_menu_id: card.verified_menu_id || "",
        logic_version: card.logic_version || state.logicVersion,
      });
      showMatchThenHandoff({
        ...data,
        image_url: data.image_url || card.image_url || "",
        has_photo: data.has_photo ?? card.has_photo,
        is_brand: data.is_brand ?? card.is_brand,
        photo_role: data.photo_role || card.photo_role,
        photo_focus: data.photo_focus || card.photo_focus,
        menu_verified: data.menu_verified ?? card.menu_verified,
        place_name: data.place_name || card.place_name,
      });
      return true;
    }
    track("swipe_nope", {
      category: card.category || "",
      pack_id: card.pack_id || state.packId,
      menu_id: card.menu_id,
      verified_menu_id: card.verified_menu_id || "",
      place_id: card.place_id || "",
      rank: card.pack_rank || state.packRank,
      logic_version: card.logic_version || state.logicVersion,
    });
    if (applyFeed(data, { req })) renderCard();
    return true;
  } catch (err) {
    console.error(err);
    setFeedHint("연결이 끊겼어요. 한 번 더 눌러 주세요.", "error");
    return false;
  } finally {
    state.swiping = false;
    setSwipeBusy(false);
    syncUndoBtn();
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
      notify("취향을 먼저 고르면 둘이서 고르기를 만들 수 있어요.", "error");
      return;
    }
    notify("초대 링크를 만드는 중이에요.", "busy");
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
    track("duo_create", {});
    try {
      await navigator.clipboard.writeText(url);
      notify("초대 링크를 복사했어요. 친구에게 붙여넣어 보내세요.");
    } catch {
      prompt("이 링크를 친구에게 보내세요", url);
    }
  } catch (err) {
    console.error(err);
    notify("초대 링크를 만들지 못했어요. 잠시 후 다시 눌러 주세요.", "error");
  }
}

/** 현재 화면에 맞는 상태 줄에 메시지를 띄운다 (없으면 alert) */
function notify(text, tone = "") {
  const onDone = !$("screen-done")?.classList.contains("hidden");
  if (onDone) {
    setShareStatus(text);
    return;
  }
  if (!$("screen-feed")?.classList.contains("hidden")) {
    $("feed-hint")?.classList.remove("hidden");
    setFeedHint(text, tone);
    return;
  }
  alert(text);
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
      title: data.receipt_title || persona.title || "본능 100% 그냥이거 마스터",
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

function buildShareText(receipt) {
  const url = receipt.share_url || "";
  const title = receipt.title || "식탐 영수증";
  const place = receipt.place_name || "";
  const menu = receipt.menu_name || "";
  const reason = receipt.match_reason || receipt.sub_text || "";
  return (
    `${title} · 그냥여기\n` +
    `${place}${menu ? ` / ${menu}` : ""}\n` +
    (reason ? `${reason}\n` : "") +
    url
  );
}

function setReceiptExpanded(open) {
  const card = $("receipt");
  const body = $("receipt-body");
  const label = $("receipt-toggle-label");
  const tog = $("btn-receipt-toggle");
  if (!card) return;
  card.classList.toggle("is-collapsed", !open);
  if (body) body.hidden = !open;
  if (label) label.textContent = open ? "접기" : "펼치기";
  if (tog) tog.setAttribute("aria-expanded", open ? "true" : "false");
}

async function shareReceipt() {
  try {
    setReceiptExpanded(true);
    const receipt = state.lastReceipt;
    if (!receipt?.share_url) {
      setShareStatus("아직 공유할 영수증이 없어요.");
      return;
    }
    const text = buildShareText(receipt);
    const payload = {
      title: "그냥여기 영수증",
      text,
      url: receipt.share_url,
    };
    if (navigator.share) {
      await navigator.share(payload);
      track("share", { channel: "native" });
      setShareStatus("공유했어요.");
      return;
    }
    await navigator.clipboard.writeText(text);
    track("share", { channel: "clipboard" });
    setShareStatus("링크 복사됐어요. 카톡·인스타에 붙여넣으면 돼요.");
  } catch (err) {
    if (err && err.name === "AbortError") return;
    try {
      const receipt = state.lastReceipt;
      await navigator.clipboard.writeText(buildShareText(receipt || {}));
      track("share", { channel: "clipboard_fallback" });
      setShareStatus("링크 복사됐어요.");
    } catch {
      setShareStatus("공유에 실패했어요. 잠시 후 다시 눌러 주세요.");
    }
  }
}

/** 스토리 인증 보상 — 골드 영수증 해금 */
function updateStoryReward() {
  const box = $("story-reward");
  const btn = $("btn-story-unlock");
  if (!box || !btn) return;
  if (state.goldUnlocked) {
    box.classList.add("is-done");
    btn.disabled = true;
    btn.textContent = "골드 영수증 적용됨";
  } else {
    box.classList.remove("is-done");
    btn.disabled = false;
    btn.textContent = "스토리 올렸어요";
  }
}

/** 올릴 이미지를 손에 쥐여 준다 — 이게 없으면 보상 루프가 성립하지 않는다 */
async function makeStoryImage() {
  const btn = $("btn-story-image");
  if (!btn || btn.disabled) return;
  if (!window.JustHereStory) {
    setShareStatus("이미지를 만들 수 없는 환경이에요. 「링크 복사」를 써 주세요.");
    return;
  }
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "만드는 중…";
  try {
    setReceiptExpanded(true);
    if (state.lastDone) await ensureReceipt(state.lastDone);
    const receipt = {
      ...(state.lastReceipt || {}),
      place_name: state.lastReceipt?.place_name || state.lastDone?.place_name,
      menu_name: state.lastReceipt?.menu_name || state.lastDone?.menu_name,
      intent: state.lastReceipt?.intent || state.intent,
    };
    const result = await window.JustHereStory.shareStoryImage(receipt, {
      gold: !!state.goldUnlocked,
    });
    track("story_image", { result });
    if (result === "shared") {
      setShareStatus("스토리에 올린 뒤 「스토리 올렸어요」를 눌러 주세요.");
    } else if (result === "saved") {
      setShareStatus("이미지를 저장했어요. 인스타 스토리에 올려 주세요.");
    } else if (result === "opened") {
      setShareStatus("새 탭의 이미지를 길게 눌러 저장한 뒤 스토리에 올려 주세요.");
    } else if (result === "failed") {
      setShareStatus("이미지를 만들지 못했어요. 잠시 후 다시 눌러 주세요.");
    }
  } catch (err) {
    console.error(err);
    setShareStatus("이미지를 만들지 못했어요. 잠시 후 다시 눌러 주세요.");
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

async function unlockStoryGold() {
  if (state.goldUnlocked) return;
  state.goldUnlocked = true;
  updateStoryReward();
  $("receipt")?.classList.add("is-gold");
  setShareStatus("골드 영수증이 적용됐어요. 다음 영수증에도 표시됩니다.");
  track("story_unlock", {});
  if (!state.uid) return;
  try {
    await api("/v1/me/unlock", {
      method: "POST",
      body: JSON.stringify({ uid: state.uid, key: "story_gold" }),
    });
  } catch (err) {
    console.warn("unlock sync failed", err);
  }
}

function showDone(data) {
  state.lastDone = data;
  show("screen-done");
  const thumb = $("done-thumb");
  const photo = usablePhoto(data);
  if (thumb) {
    if (photo) {
      thumb.src = photo.url;
      thumb.alt = data.place_name || "";
      thumb.classList.remove("hidden");
      thumb.onerror = () => {
        thumb.removeAttribute("src");
        thumb.classList.add("hidden");
      };
    } else {
      thumb.removeAttribute("src");
      thumb.classList.add("hidden");
    }
  }
  $("done-sub").textContent = `${data.place_name} · ${displayMenuName(data)}`;
  const persona = data.persona || {};
  const title = data.receipt_title || persona.title || "본능 100% 그냥이거 마스터";
  $("receipt-title").textContent = title;
  $("receipt-sub").textContent = persona.sub_text || data.receipt?.sub_text || "";
  $("receipt-sticker").textContent =
    persona.sticker || data.receipt?.sticker || "🛋️";
  $("receipt-place").textContent = data.place_name || "";
  $("receipt-menu").textContent = displayMenuName(data);
  $("receipt-reason").textContent =
    persona.match_reason || data.receipt?.match_reason || "근처 매칭 완료";
  const theme =
    persona.asset_id ||
    persona.theme ||
    data.receipt?.asset_id ||
    data.receipt?.theme ||
    "bg_basic";
  const card = $("receipt");
  card.className = `receipt-card theme-${theme} is-collapsed${state.goldUnlocked ? " is-gold" : ""}`;
  setReceiptExpanded(false);
  const tog = $("btn-receipt-toggle");
  if (tog) tog.onclick = () => setReceiptExpanded(card.classList.contains("is-collapsed"));
  const link = $("handoff-link");
  link.href = data.handoff.url;
  const delivery = data.handoff.intent === "delivery" || data.is_brand;
  link.textContent = delivery
    ? "공식 주문 페이지 열기"
    : "지도에서 확인";
  link.onclick = () => {
    track("handoff_open", {
      intent: data.handoff?.intent || state.intent,
      pack_id: data.pack_id || state.packId,
      logic_version: data.logic_version || state.logicVersion,
      provider: data.handoff?.provider || "",
    });
  };
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
  updateKakaoLinkButton();
  updateStoryReward();
  refreshTitleBadge();
  if (isDesignPreview()) {
    setShareStatus("");
    $("meal-prompt")?.classList.add("hidden");
    return;
  }
  renderMealPrompt(data);
  ensureReceipt(data)
    .then(() => setShareStatus("공유할 준비됐어요"))
    .catch(() => setShareStatus("공유 링크를 아직 못 만들었어요"));
}

function mealStorageKey(data) {
  const uid = state.uid || window.JustHereAuth?.getUid?.() || "";
  const menu = data?.menu_id || data?.place_name || "";
  const day = new Date().toISOString().slice(0, 10);
  return `jh_meal:${uid}:${menu}:${day}`;
}

function renderMealPrompt(data) {
  const box = $("meal-prompt");
  if (!box) return;
  const uid = state.uid || window.JustHereAuth?.getUid?.() || "";
  const answered = !!(data && localStorage.getItem(mealStorageKey(data)));
  box.classList.toggle("hidden", !uid || answered);
}

async function submitMeal(eaten) {
  const data = state.lastDone;
  const uid = state.uid || window.JustHereAuth?.getUid?.() || "";
  const box = $("meal-prompt");
  if (!data || !uid || !box || box.classList.contains("hidden")) return;
  const yes = $("btn-meal-yes");
  const skip = $("btn-meal-skip");
  if (yes) yes.disabled = true;
  if (skip) skip.disabled = true;
  try {
    await api("/v1/me/meal", {
      method: "POST",
      body: JSON.stringify({
        uid,
        menu_id: data.menu_id || "",
        category: data.category || "",
        kind: data.kind || "",
        place_name: data.place_name || "",
        eaten: !!eaten,
      }),
    });
    localStorage.setItem(mealStorageKey(data), eaten ? "ate" : "skip");
    track("meal_confirm", {
      eaten: !!eaten,
      category: data.category || "",
      menu_id: data.menu_id || "",
      pack_id: data.pack_id || state.packId,
      logic_version: data.logic_version || state.logicVersion,
    });
    box.innerHTML = eaten
      ? "<p class=\"meal-prompt-title\">다음 식사 때 참고할게요</p><p class=\"meal-prompt-sub\">오늘은 다른 종류를 조금 앞에 두고, 나중에 비슷한 걸 더 자주 보여드려요.</p>"
      : "<p class=\"meal-prompt-title\">알겠어요</p><p class=\"meal-prompt-sub\">지금은 선택만 저장해 둘게요.</p>";
  } catch (err) {
    console.error(err);
    if (yes) yes.disabled = false;
    if (skip) skip.disabled = false;
    setShareStatus("식사 확인을 저장하지 못했어요. 다시 눌러 주세요.");
  }
}

function setSwipeDir(dx) {
  const dir = $("swipe-dir");
  const el = $("card");
  if (!dir || !el) return;
  el.classList.remove("is-pass", "is-go");
  dir.classList.remove("is-pass", "is-go");
  if (Math.abs(dx) < 28) {
    dir.classList.add("hidden");
    dir.textContent = "";
    return;
  }
  const go = dx > 0;
  const view = cardPresentation(currentCard() || {});
  dir.textContent = go ? view.go : view.pass;
  dir.classList.remove("hidden");
  dir.classList.add(go ? "is-go" : "is-pass");
  el.classList.add(go ? "is-go" : "is-pass");
}

function setupSwipeGestures() {
  const el = $("card");
  let startX = 0;
  let startY = 0;
  let dx = 0;
  let dy = 0;
  let active = false;
  let axis = "";

  const resetCard = () => {
    el.style.transform = "";
    el.style.opacity = "1";
    setSwipeDir(0);
  };
  const blocked = (target) =>
    !!(target?.closest && target.closest("#btn-card-detail, #detail, button, a"));
  const onStart = (x, y, target) => {
    if ($("detail") && !$("detail").classList.contains("hidden")) return;
    if (state.swiping || state.modeSwitching) return;
    if (blocked(target)) return;
    active = true;
    axis = "";
    startX = x;
    startY = y;
    dx = 0;
    dy = 0;
  };
  const onMove = (x, y) => {
    if (!active) return;
    dx = x - startX;
    dy = y - startY;
    if (!axis) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      axis = Math.abs(dy) > Math.abs(dx) ? "y" : "x";
    }
    if (axis === "y") {
      setSwipeDir(0);
      return;
    }
    if (prefersReducedMotion()) {
      setSwipeDir(dx);
      return;
    }
    el.style.transition = "none";
    el.style.transform = `translateX(${dx}px)`;
    el.style.opacity = String(Math.max(0.55, 1 - Math.abs(dx) / 360));
    setSwipeDir(dx);
  };
  const onEnd = async () => {
    if (!active) return;
    active = false;
    const horizontal = axis === "x";
    axis = "";
    el.style.transition = "";
    if (!horizontal || Math.abs(dx) <= 100) {
      resetCard();
      return;
    }
    markSwipeHintSeen();
    const moved = await swipe(dx > 0 ? "lets_go" : "nope");
    if (!moved) resetCard();
    else resetCard();
  };

  el.addEventListener(
    "touchstart",
    (e) => onStart(e.touches[0].clientX, e.touches[0].clientY, e.target),
    { passive: true }
  );
  el.addEventListener(
    "touchmove",
    (e) => onMove(e.touches[0].clientX, e.touches[0].clientY),
    { passive: true }
  );
  el.addEventListener("touchend", onEnd);
  el.addEventListener("mousedown", (e) => onStart(e.clientX, e.clientY, e.target));
  window.addEventListener("mousemove", (e) => onMove(e.clientX, e.clientY));
  window.addEventListener("mouseup", onEnd);
}

function setupCardKeys() {
  document.addEventListener("keydown", (e) => {
    const feed = $("screen-feed");
    if (!feed || feed.classList.contains("hidden")) return;
    if (e.key === "Escape") {
      hideDetailModal();
      return;
    }
    const tag = (e.target && e.target.tagName) || "";
    if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      $("btn-nope")?.focus();
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      $("btn-go")?.focus();
    }
  });
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderDetailModal(card) {
  const d = $("detail");
  if (!d || !card) return;
  const pct = card.sensitivity_percent != null
    ? card.sensitivity_percent
    : Math.round(Number(card.delivery_sensitivity || 0) * 100);
  const level = card.sensitivity_level || "무난해요";
  const tip =
    card.sensitivity_tip ||
    "식으면 맛이 얼마나 달라지는지예요. 배달 거리를 알 수는 없어요.";
  /* 브랜드는 지점이 아니라 브랜드다 — 주소·거리를 채워 넣으면 거짓이 된다 */
  const sourceLabel = card.is_brand
    ? "공식 주문"
    : SOURCE_LABELS[state.inventorySource] ||
      SOURCE_LABELS[card.source] ||
      card.source ||
      "—";
  const visitKind = [
    ["종류", kindLabel(card)],
    card.inferred_kind && card.inferred_kind !== categoryLabel(card)
      ? ["카카오 분류(추정)", card.inferred_kind]
      : null,
    ["주소", card.address || "주소 확인 중"],
    ["영업시간", card.hours || "카카오맵에서 확인"],
    ["거리", `${distanceLabel(card.distance_m)} · ${card.eta_label || "—"}`],
    ["반경", state.radius ? `${state.radius}m` : "—"],
    ["가격", priceFact(card)],
    ["출처", sourceLabel],
  ].filter(Boolean);
  const rows = card.is_brand
    ? [
        ["종류", card.kind || categoryLabel(card)],
        ["대표 메뉴", card.menu_name || "—"],
        ["주문 채널", card.order_channel || "공식 주문"],
        ["가격", priceFact(card)],
        ["출처", sourceLabel],
      ]
    : visitKind;
  const kindName = excludeLabel(card.kind || card.category);
  const excluded = (state.excludeCats || []).includes(String(card.kind || "").trim());
  d.innerHTML = `
    <div class="detail-head">
      <strong>${escapeHtml(card.place_name)}</strong>
      <button type="button" class="detail-close" id="detail-close" aria-label="닫기">✕</button>
    </div>
    <div class="detail-grid">
      ${rows
        .map(
          ([k, v]) =>
            `<div class="detail-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`
        )
        .join("")}
    </div>
    ${
      card.is_brand
        ? `<div class="sens-box">
      <div class="sens-title">
        <span>식으면</span>
        <span>${escapeHtml(level)}</span>
      </div>
      <div class="sens-gauge" aria-hidden="true"><span style="width:${pct}%"></span></div>
      <p class="sens-tip">${escapeHtml(tip)}</p>
    </div>`
        : ""
    }
    <button type="button" class="btn ghost detail-exclude" id="btn-exclude-kind">
      ${excluded ? `${escapeHtml(kindName)} 다시 추천하기` : `${escapeHtml(kindName)}, 안 먹어요`}
    </button>
  `;
  d.classList.remove("hidden");
  const close = $("detail-close");
  if (close) {
    close.onclick = (e) => {
      e.stopPropagation();
      hideDetailModal();
    };
    close.focus();
  }
  const ex = document.getElementById("btn-exclude-kind");
  if (ex) {
    ex.onclick = (e) => {
      e.stopPropagation();
      submitExclude(card);
    };
  }
}

function hideDetailModal() {
  const d = $("detail");
  if (!d || d.classList.contains("hidden")) return;
  d.classList.add("hidden");
  $("btn-card-detail")?.focus();
}

function setupLongPress() {
  const el = $("card");
  let timer = null;
  let moved = false;
  const clear = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  const open = () => {
    const card = currentCard();
    if (!card) return;
    renderDetailModal(card);
  };

  const detailBtn = $("btn-card-detail");
  if (detailBtn) {
    detailBtn.onclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      open();
    };
  }

  el.addEventListener(
    "touchstart",
    (e) => {
      if (e.target.closest && e.target.closest("#btn-card-detail")) return;
      moved = false;
      clear();
      timer = setTimeout(open, 450);
    },
    { passive: true }
  );
  el.addEventListener(
    "touchmove",
    () => {
      moved = true;
      clear();
    },
    { passive: true }
  );
  el.addEventListener("touchend", () => {
    clear();
  });
  el.addEventListener("mousedown", (e) => {
    if (e.target.closest && e.target.closest("#btn-card-detail")) return;
    moved = false;
    clear();
    timer = setTimeout(open, 450);
  });
  el.addEventListener("mouseup", clear);
  el.addEventListener("mouseleave", clear);
  el.addEventListener("click", (e) => {
    if (e.target.closest && e.target.closest("#btn-card-detail")) return;
    const d = $("detail");
    if (d && !d.classList.contains("hidden")) {
      if (e.target.closest && e.target.closest("#detail-close")) return;
      if (e.target.closest && e.target.closest("#btn-exclude-kind")) return;
      if (!moved) hideDetailModal();
    }
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
  });

  // iOS / 이미 설치됨: 안내만
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;
  if (isStandalone) {
    hideBtn();
  }

  btn.onclick = async () => {
    track("install_click", { has_prompt: !!deferred });
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

const EXAMPLE_PHOTOS = {
  doenjang: {
    id: "doenjang-jjigae",
    url: "/static/example-photos/doenjang-jjigae.jpg",
    credit: "Alpha (Flickr)",
    license: "CC BY-SA 2.0",
    source_url: "https://commons.wikimedia.org/wiki/File:Korean_stew-Doenjang_jjigae-01.jpg",
    representative: true,
    is_menu_photo: true,
    menu_match: "된장찌개",
    use: "verified_menu_or_preview",
    caption: "",
  },
  chicken: {
    id: "chicken",
    url: "/static/example-photos/chicken.jpg",
    remote_url: "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=1200&q=80",
    credit: "Unsplash",
    license: "Unsplash License",
    source_url: "https://unsplash.com/photos/fried-chicken-on-white-ceramic-plate-2s6ORaJNNm0",
    representative: true,
    is_menu_photo: false,
    menu_match: "",
    use: "brand_example_only",
    caption: "음식 종류 예시",
  },
};

function designCard(kind) {
  const doenjang = EXAMPLE_PHOTOS.doenjang;
  const chicken = EXAMPLE_PHOTOS.chicken;
  if (kind === "photo") {
    return {
      card_id: "design-photo",
      menu_id: "design-menu",
      place_name: "송도 뚝배기집",
      menu_name: "된장찌개",
      menu_verified: true,
      price_krw: 12000,
      price_band: "1.2만원",
      price_source: "listed",
      distance_m: 240,
      eta_label: "도보 약 3분",
      category: "korean",
      kind: "한식",
      address: "인천 연수구 컨벤시아대로 165",
      hours: "11:00–21:00",
      why: "지금 위치에서 걸어갈 수 있는 곳이에요.",
      image_url: doenjang.url,
      has_photo: true,
      photo_role: "menu",
      photo_is_menu: true,
      photo_focus: "50% 42%",
      pack_rank: 1,
    };
  }
  if (kind === "brand") {
    return {
      card_id: "design-brand",
      menu_id: "brand:kyochon",
      place_name: "교촌치킨",
      menu_name: "교촌 오리지날",
      is_brand: true,
      kind: "치킨",
      category: "meat",
      order_channel: "교촌 공식 주문",
      price_krw: 20000,
      price_band: "2만원",
      price_source: "estimated",
      why: "",
      image_url: chicken.url,
      has_photo: true,
      photo_role: "example",
      photo_is_menu: false,
      photo_focus: "50% 35%",
      pack_rank: 1,
    };
  }
  if (kind === "nophoto") {
    return {
      card_id: "design-nophoto",
      menu_id: "design-store",
      place_name: "센트럴파크 한식당",
      menu_name: "한식",
      category: "korean",
      kind: "한식",
      distance_m: 180,
      eta_label: "도보 약 2분",
      price_source: "unknown",
      address: "인천 연수구 센트럴로 123",
      hours: "11:00–21:30",
      why: "지금 위치에서 걸어갈 수 있는 곳이에요.",
      has_photo: false,
      pack_rank: 1,
    };
  }
  return {
    card_id: "design-long",
    menu_id: "design-long",
    place_name: "송도국제도시 센트럴파크 옆 아주아주긴이름의 저녁밥상 한정식",
    menu_name: "한식",
    category: "korean",
    kind: "한식",
    distance_m: 640,
    eta_label: "도보 약 8분",
    price_source: "unknown",
    address: "인천 연수구 송도과학로 123-45 1층",
    why: "",
    has_photo: false,
    pack_rank: 2,
  };
}

function openDesignPreview() {
  const params = new URLSearchParams(window.location.search);
  const kind = params.get("design");
  if (!kind) return false;
  const intro = $("intro");
  if (intro) intro.remove();
  state.designPreview = true;
  state.uid = "";
  state.intent = kind === "brand" || kind === "done-delivery" ? "delivery" : "visit";
  state.mealContext = "meal";
  state.radius = 700;
  state.packSize = 3;
  state.inventorySource = state.intent === "delivery" ? "brand" : "kakao";
  state.sessionId = "design-preview";
  setToggleUI(state.intent);
  setMealUI(state.mealContext);
  setupSwipeGestures();
  setupLongPress();
  setupCardKeys();

  if (kind === "adjust") {
    state.adjustNeeded = true;
    state.canUndo = true;
    state.packRank = 3;
    state.adjustOptions = [
      { id: "cheaper", label: "더 저렴하게" },
      { id: "different", label: "다른 종류로" },
      { id: "closer", label: "더 가까운 곳" },
      { id: "again", label: "조건 그대로 다시" },
    ];
    show("screen-feed");
    renderFeedChrome();
    renderCard();
    return true;
  }

  if (kind === "done" || kind === "done-delivery") {
    const card = designCard(kind === "done-delivery" ? "brand" : "photo");
    showDone({
      ...card,
      receipt_title: "본능 100% 그냥이거 마스터",
      persona: { sub_text: "근처에서 바로 골랐어요", sticker: "🛋️", theme: "bg_basic" },
      receipt: { match_reason: "확인된 메뉴와 거리가 맞았어요" },
      handoff:
        kind === "done-delivery"
          ? {
              intent: "delivery",
              url: "https://www.kyochon.com/order",
              cta: "공식 주문 페이지 열기",
              note: "교촌 공식 주문으로 이동해요. 배달앱에서 다시 찾지 않아도 돼요.",
            }
          : {
              intent: "visit",
              url: "https://map.kakao.com/",
              cta: "지도에서 확인",
            },
    });
    return true;
  }

  const card = designCard(kind);
  state.cards = [card];
  state.packRank = card.pack_rank || 1;
  state.canUndo = kind !== "photo";
  show("screen-feed");
  renderFeedChrome();
  renderCard();
  return true;
}

init()
  .catch((err) => {
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
  })
  // 실패해도 주황 화면에 갇히면 안 된다
  .finally(() => dismissIntro());
