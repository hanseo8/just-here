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

function openTasteFlow() {
  $("start-panel").classList.add("hidden");
  $("taste-stage").classList.remove("hidden");
  const hero = document.querySelector(".brand-hero");
  if (hero) hero.classList.add("compact");
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
    btn.className = `taste-cat${selected.has(c.key) ? " on" : ""}`;
    btn.dataset.key = c.key;
    btn.innerHTML = `<span class="taste-cat-name">${c.label}</span>`;
    btn.onclick = () => toggleTasteCategory(c.key);
    box.appendChild(btn);
  });
  syncTasteCatNext();
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
  renderTasteCategories();
}

function syncTasteCatNext() {
  const cats = state.tasteChoices.filter((k) =>
    TASTE_CATEGORIES.some((c) => c.key === k)
  );
  const n = cats.length;
  const hint = $("taste-cat-hint");
  if (hint) hint.textContent = `${n} / ${TASTE_CAT_MAX}`;
  const next = $("btn-taste-next");
  if (!next) return;
  next.disabled = n < TASTE_CAT_MIN;
  next.classList.toggle("ready", n >= TASTE_CAT_MIN);
  if (n === 0) {
    next.textContent = `원하는 종류를 눌러보세요 (${n}/${TASTE_CAT_MAX})`;
  } else if (n < TASTE_CAT_MIN) {
    next.textContent = `하나 더 고르면 시작해요 (${n}/${TASTE_CAT_MAX})`;
  } else {
    next.textContent = "선택 완료 · 시작";
  }
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
  await startSession();
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

    // 저장된 취향이 있으면 스킵 (다시 고르기만 예외)
    const reuse =
      !state.forceRetaste &&
      (state.savedTaste?.length >= 1 || state.tasteChoices?.length >= 1);
    if (reuse) {
      if (!state.tasteChoices?.length) {
        state.tasteChoices = [...state.savedTaste];
      }
      btn.disabled = false;
      btn.textContent = "시작하기";
      await startSession();
      return;
    }

    btn.disabled = false;
    btn.textContent = "시작하기";
    openTasteFlow();
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

async function locateAndSyncWeather(force = true) {
  const btn = $("btn-locate");
  const retry = $("btn-retry-loc");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "위치 파악 중…";
  }
  setLocStatus("현재 위치를 확인합니다…");
  try {
    await requestLocation(force);
    if (retry) retry.classList.remove("hidden");
    setLocStatus(
      state.usingFallbackLoc
        ? "위치 권한이 없어 송도 기준으로 맞춰 뒀어요. 가능하면 권한을 허용해 주세요."
        : `위치 파악 완료 · ${state.lat.toFixed(5)}, ${state.lng.toFixed(5)}`,
      !state.usingFallbackLoc
    );
    await applySmartIntent();
    startWatchingLocation();
    if ($("btn-start")) $("btn-start").disabled = false;
  } catch (err) {
    console.error(err);
    useFallbackLocation("위치를 가져오지 못했어요");
    await applySmartIntent().catch(() => {});
    if ($("btn-start")) $("btn-start").disabled = false;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "위치 파악";
    }
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
        const hint = $("taste-reuse-hint");
        if (hint) {
          hint.textContent = "카카오 도감 저장 완료. 저장된 취향으로 바로 시작할 수 있어요.";
          hint.classList.remove("hidden");
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
        } catch (_) {}
      }
      updateTasteReuseHint();
    }
  } catch (err) {
    console.warn("guest auth skipped", err);
  }
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
  const locateBtn = $("btn-locate");
  if (locateBtn) locateBtn.onclick = () => locateAndSyncWeather(true);
  $("btn-retry-loc").onclick = () => locateAndSyncWeather(true);
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
  const reloadBtn = $("btn-reload-feed");
  if (reloadBtn) {
    reloadBtn.onclick = async () => {
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
      }
    };
  }

  document.querySelectorAll(".tog").forEach((btn) => {
    btn.onclick = async () => {
      if (state.swiping || state.modeSwitching) return;
      const next = btn.dataset.intent;
      if (!next || next === state.intent) return;
      state.modeSwitching = true;
      state.intent = next;
      state.intentReason = "";
      setToggleUI(state.intent);
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
  const ws = $("weather-status");
  if (ws) ws.textContent = "위치 파악 후 날씨가 자동으로 연동됩니다.";
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

function updateTasteReuseHint() {
  const hint = $("taste-reuse-hint");
  const retaste = $("btn-retaste");
  const has = (state.savedTaste?.length || 0) >= 1;
  if (hint) hint.classList.toggle("hidden", !has);
  if (retaste) retaste.classList.toggle("hidden", !has);
  if (has && $("btn-start") && !state.forceRetaste) {
    $("btn-start").textContent = "저장된 취향으로 시작";
  }
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
        uid: state.uid || undefined,
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
    `인스타 스토리에 올리면 JUSTHERE10\n` +
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
      setShareStatus("공유했어요.");
      return;
    }
    await navigator.clipboard.writeText(text);
    setShareStatus("링크 복사됐어요. 카톡·인스타에 붙여넣으면 돼요.");
  } catch (err) {
    if (err && err.name === "AbortError") return;
    try {
      const receipt = state.lastReceipt;
      await navigator.clipboard.writeText(buildShareText(receipt || {}));
      setShareStatus("링크 복사됐어요.");
    } catch {
      setShareStatus("공유에 실패했어요. 잠시 후 다시 눌러 주세요.");
    }
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
  updateKakaoLinkButton();
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

  const onStart = (x) => {
    if ($("detail") && !$("detail").classList.contains("hidden")) return;
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
  if (close) close.onclick = (e) => {
    e.stopPropagation();
    hideDetailModal();
  };
}

function hideDetailModal() {
  const d = $("detail");
  if (d) d.classList.add("hidden");
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

  el.addEventListener(
    "touchstart",
    () => {
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
  el.addEventListener("mousedown", () => {
    moved = false;
    clear();
    timer = setTimeout(open, 450);
  });
  el.addEventListener("mouseup", clear);
  el.addEventListener("mouseleave", clear);
  el.addEventListener("click", (e) => {
    const d = $("detail");
    if (d && !d.classList.contains("hidden")) {
      if (e.target.closest && e.target.closest("#detail-close")) return;
      // 상세가 열린 상태에서 카드 탭하면 닫기
      if (!moved) hideDetailModal();
    }
  });
}

async function shareForInstagramStory() {
  return shareReceipt();
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
