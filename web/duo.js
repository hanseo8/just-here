const $ = (id) => document.getElementById(id);
const duoId = location.pathname.split("/").filter(Boolean).pop();

const state = {
  meta: null,
  tasteIndex: 0,
  tasteChoices: [],
  room: null,
  role: "guest", // host | guest
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function show(id) {
  ["stage-taste", "stage-wait", "stage-result"].forEach((s) =>
    $(s).classList.add("hidden")
  );
  $(id).classList.remove("hidden");
}

function renderTaste() {
  const pairs = state.meta.taste_pairs;
  if (state.tasteIndex >= pairs.length) {
    finishTaste();
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

async function finishTaste() {
  if (state.role === "guest") {
    $("duo-sub").textContent = "교집합 계산 중…";
    const room = await api(`/v1/duo/${duoId}/join`, {
      method: "POST",
      body: JSON.stringify({
        taste: state.tasteChoices,
        guest_name: "친구",
      }),
    });
    state.room = room;
    showResult(room);
    return;
  }
  // host already created before taste in app.js flow — this page is mainly guest
}

function showResult(room) {
  if (!room.pick) {
    show("stage-wait");
    $("wait-msg").textContent =
      "아직 공통 추천을 못 찾았어요. 잠시 후 새로고침 해 보세요.";
    return;
  }
  show("stage-result");
  const p = room.pick;
  $("pick-img").src = p.image_url || "";
  $("pick-place").textContent = p.place_name;
  $("pick-menu").textContent = p.menu_name;
  $("pick-eta").textContent = p.eta_label || "";
  $("pick-reason").textContent = p.match_reason || "";
  $("pick-map").href = p.map_url;
  $("duo-sub").textContent = `${room.host_name} × ${room.guest_name || "친구"}의 원픽`;
}

async function init() {
  state.meta = await api("/v1/meta");
  // 서버 pairs 없으면 프론트만으로는 불가 → meta에 있음
  if (!state.meta.taste_pairs?.length) {
    alert("취향 데이터를 불러오지 못했어요.");
    return;
  }
  try {
    state.room = await api(`/v1/duo/${duoId}`);
  } catch {
    $("duo-sub").textContent = "초대 링크가 만료됐거나 잘못됐어요.";
    return;
  }

  if (state.room.status === "matched" && state.room.pick) {
    showResult(state.room);
    return;
  }

  // 게스트: 취향 선택
  state.role = "guest";
  $("duo-sub").textContent = `${state.room.host_name}님이 초대했어요. 취향 4장만 골라 주세요.`;
  show("stage-taste");
  renderTaste();

  $("btn-copy-invite").onclick = async () => {
    try {
      await navigator.clipboard.writeText(state.room.invite_url);
      $("copy-status").textContent = "복사 완료";
      $("copy-status").classList.remove("hidden");
    } catch {
      $("copy-status").textContent = "복사 실패";
      $("copy-status").classList.remove("hidden");
    }
  };
  $("btn-poll").onclick = async () => {
    state.room = await api(`/v1/duo/${duoId}`);
    if (state.room.pick) showResult(state.room);
  };
}

init().catch((err) => {
  console.error(err);
  $("duo-sub").textContent = "연결 실패. 서버가 켜져 있는지 확인해 주세요.";
});
