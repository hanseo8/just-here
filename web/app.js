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
  lastDone: null,
  savedTaste: [],
  forceRetaste: false,
  goldUnlocked: false,
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

/** 소프트런치 퍼널 이벤트 — 실패해도 UX 방해 없음 */
function track(event, props = {}) {
  try {
    const body = {
      event,
      uid: state.uid || window.JustHereAuth?.getUid?.() || "",
      device_id: window.JustHereAuth?.getDeviceId?.() || "",
      props: props || {},
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

let feedHintDefault = null;

/** 피드 하단 한 줄을 안내·진행·실패 메시지로 함께 쓴다 */
function setFeedHint(text, tone = "") {
  const el = $("feed-hint");
  if (!el) return;
  if (feedHintDefault === null) feedHintDefault = el.textContent;
  el.textContent = text || feedHintDefault;
  el.classList.toggle("is-error", tone === "error");
  el.classList.toggle("is-busy", tone === "busy");
}

/** 카드 액션 진행 중: 중복 탭 차단 + 무슨 일이 일어나는지 표시 */
function setSwipeBusy(busy, action) {
  const pass = $("btn-nope");
  const go = $("btn-go");
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
    setToggleUI(state.intent);
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

const TASTE_CAT_MIN = 2;
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
    .querySelectorAll(".taste-tone, #btn-taste-skip-tone, #btn-taste-back")
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
  const imageUrl = `${location.origin}/static/icons/icon-512.png`;
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
  $("btn-start").disabled = true;
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
        const data = await api("/v1/session", {
          method: "POST",
          body: JSON.stringify({
            lat: state.lat,
            lng: state.lng,
            intent: state.intent,
            weather: state.weather,
            taste: state.tasteChoices,
            uid: state.uid || undefined,
          }),
        });
        applyFeed(data);
        setToggleUI(state.intent);
        renderCard();
      } catch (err) {
        console.error(err);
        const msg = $("empty-msg");
        if (msg) msg.textContent = "다시 불러오지 못했어요. 잠시 후 시도해 주세요.";
      } finally {
        reloadBtn.disabled = false;
        reloadBtn.textContent = "다시 불러오기";
      }
    };
  }

  const emptySwap = $("btn-empty-intent");
  if (emptySwap) {
    emptySwap.onclick = () => {
      document.querySelector(".tog:not(.on)")?.click();
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
          ? "배달 가능한 곳으로 다시 찾는 중이에요."
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
  syncStartState();
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
  $("radius-label").textContent = `${state.radius}m`;
  $("slots-label").textContent = `${state.perfect}/5`;
  if ($("source-label")) {
    const srcMap = {
      hub_seed: "송도 큐레이션",
      hub_seed_anchored: "송도 · 내위치",
      "hub+kakao": "송도 + 주변",
      kakao: "주변 실상호",
      seed_fallback: "라이트",
    };
    $("source-label").textContent =
      srcMap[data.inventory_source] || data.inventory_source || "—";
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
  if (!card) {
    el.classList.add("hidden");
    empty.classList.remove("hidden");
    const msg = $("empty-msg");
    if (msg) {
      msg.textContent = state.usingFallbackLoc
        ? `송도 기준 ${state.radius}m 안에서 조건에 맞는 가게를 못 찾았어요. 위치를 다시 잡으면 결과가 달라져요.`
        : `${state.radius}m 안에서 조건에 맞는 가게를 못 찾았어요.`;
    }
    const swapBtn = $("btn-empty-intent");
    if (swapBtn) {
      swapBtn.textContent =
        state.intent === "delivery" ? "방문으로 바꿔 보기" : "배달로 바꿔 보기";
    }
    // 카드가 없으면 스와이프 안내는 의미 없음
    $("feed-hint")?.classList.add("hidden");
    return;
  }
  $("feed-hint")?.classList.remove("hidden");
  setFeedHint("");
  empty.classList.add("hidden");
  el.classList.remove("hidden");
  el.classList.toggle("gold", !!card.is_gold);
  $("gold-badge").classList.toggle("hidden", !card.is_gold);
  setCardMedia(card);
  $("card-place").textContent = card.place_name;
  $("card-menu").textContent = card.menu_name;
  $("card-eta").textContent = card.eta_label;
  // 이유가 있을 때만 태그를 보여준다 (#그냥여기 같은 빈 태그는 정보가 없음)
  const tagText = card.taste_match
    ? "취향 맞춤"
    : readableTag(card.hashtag) ||
      (card.source === "kakao" ? "근처 실제 상호" : "");
  const tagEl = $("card-tag");
  tagEl.textContent = tagText;
  tagEl.classList.toggle("hidden", !tagText);
  $("detail").classList.add("hidden");
  el.style.transform = "";
  el.style.opacity = "1";
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
  flash.classList.remove("hidden");

  window.setTimeout(() => {
    flash.classList.add("hidden");
    showDone(data);
  }, 700);
}

/** @returns {Promise<boolean>} 카드가 실제로 넘어갔는지 */
async function swipe(action) {
  const card = currentCard();
  if (!card || state.swiping) return false;
  state.swiping = true;
  setSwipeBusy(true, action);
  try {
    const data = await api("/v1/swipe", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        card_id: card.card_id,
        menu_id: card.menu_id,
        action,
        uid: state.uid || undefined,
      }),
    });
    if (action === "lets_go") {
      track("swipe_go", {
        category: card.category || card.category_path?.[0] || "",
        place: card.name || "",
      });
      track("match_done", {
        category: card.category || card.category_path?.[0] || "",
        intent: state.intent,
        persona: data.persona?.id || "",
        place: data.place_name || card.name || "",
      });
      showMatchThenHandoff(data);
      return true;
    }
    track("swipe_nope", {
      category: card.category || card.category_path?.[0] || "",
    });
    applyFeed(data);
    renderCard();
    return true;
  } catch (err) {
    console.error(err);
    setFeedHint("연결이 끊겼어요. 한 번 더 눌러 주세요.", "error");
    return false;
  } finally {
    state.swiping = false;
    setSwipeBusy(false);
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

async function shareReceipt() {
  try {
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

/** 배달 모드: 딥링크 대신 상호 복사 → 배달앱 검색 */
function setupDeliveryHandoff(handoff) {
  const btn = $("btn-delivery");
  const apps = $("delivery-apps");
  const mapLink = $("handoff-link");
  if (!btn || !apps) return;

  const isDelivery = handoff?.intent === "delivery";
  btn.classList.toggle("hidden", !isDelivery);
  apps.classList.add("hidden");
  apps.innerHTML = "";
  mapLink.className = isDelivery ? "btn ghost" : "btn primary";
  if (!isDelivery) return;

  const query = handoff.search_query || state.lastDone?.place_name || "";
  btn.textContent = "배달앱에서 주문하기";
  btn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(query);
      setShareStatus(`「${query}」 복사했어요. 배달앱에서 붙여넣어 검색하세요.`);
    } catch (_) {
      setShareStatus(`배달앱에서 「${query}」로 검색하세요.`);
    }
    track("delivery_copy", { place: query });
    apps.innerHTML = (handoff.delivery_apps || [])
      .map(
        (a) =>
          `<a href="${a.url}" target="_blank" rel="noopener">${escapeHtml(a.label)}</a>`
      )
      .join("");
    apps.classList.toggle("hidden", !apps.innerHTML);
  };
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
  $("done-sub").textContent = `${data.place_name} · ${data.menu_name}`;
  const persona = data.persona || {};
  const title = data.receipt_title || persona.title || "본능 100% 그냥이거 마스터";
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
  card.className = `receipt-card theme-${theme}${state.goldUnlocked ? " is-gold" : ""}`;
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
  setupDeliveryHandoff(data.handoff);
  setShareStatus("");
  updateKakaoLinkButton();
  updateStoryReward();
  refreshTitleBadge();
  ensureReceipt(data)
    .then(() => setShareStatus("공유할 준비됐어요"))
    .catch(() => setShareStatus("공유 링크를 아직 못 만들었어요"));
}

function setupSwipeGestures() {
  const el = $("card");
  let startX = 0;
  let dx = 0;
  let active = false;

  const resetCard = () => {
    el.style.transform = "";
    el.style.opacity = "1";
  };
  const onStart = (x) => {
    if ($("detail") && !$("detail").classList.contains("hidden")) return;
    if (state.swiping || state.modeSwitching) return;
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
    if (Math.abs(dx) <= 100) {
      resetCard();
      return;
    }
    // 실패하면 카드가 밀려난 채로 남지 않도록 원위치시킨다
    const moved = await swipe(dx > 0 ? "lets_go" : "nope");
    if (!moved) resetCard();
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
  const level = card.sensitivity_level || "보통";
  const tip =
    card.sensitivity_tip ||
    "배달 중 맛·형태가 얼마나 변하는지 보여주는 지표예요.";
  const rating =
    card.rating != null ? Number(card.rating).toFixed(1) : "—";
  d.innerHTML = `
    <div class="detail-head">
      <strong>${escapeHtml(card.place_name)}</strong>
      <button type="button" class="detail-close" id="detail-close" aria-label="닫기">✕</button>
    </div>
    <div class="detail-grid">
      <div class="detail-row"><span class="k">영업시간</span><span class="v">${escapeHtml(card.hours || "확인 중")}</span></div>
      <div class="detail-row"><span class="k">실시간 평점</span><span class="v">★ ${escapeHtml(rating)}</span></div>
      <div class="detail-row"><span class="k">주소</span><span class="v">${escapeHtml(card.address || card.review || "주소 확인 중")}</span></div>
      <div class="detail-row"><span class="k">예상 가격</span><span class="v">${escapeHtml(card.price_band || "확인 중")} / 1인</span></div>
    </div>
    <div class="sens-box">
      <div class="sens-title">
        <span>배달 민감도</span>
        <span>${escapeHtml(level)} · ${pct}%</span>
      </div>
      <div class="sens-gauge" aria-hidden="true"><span style="width:${pct}%"></span></div>
      <p class="sens-tip">${escapeHtml(tip)}</p>
    </div>
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
