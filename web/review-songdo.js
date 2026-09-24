function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function userCard(card, badge) {
  const el = document.createElement("section");
  el.className = "user-shell";
  el.innerHTML = `
    <article class="card">
      <div class="card-face">
        <h2 class="card-title">${esc(card.menu_name)}</h2>
        <p class="card-sub">${esc(card.name || card.place_name)}</p>
        <dl class="card-facts">
          <div><dt>거리</dt><dd>${esc(card.eta_label || "거리 미확인")}</dd></div>
          <div><dt>가격</dt><dd>${esc(card.price_display || "가격 확인 필요")}</dd></div>
        </dl>
        <p class="note">${esc(card.why || "")}</p>
      </div>
    </article>
    <p class="internal">내부 상태 · ${esc(badge || "사진 확보 전")} · ${esc(card.address || "")}</p>
  `;
  return el;
}

function fill(id, cards, badge) {
  const root = document.getElementById(id);
  root.replaceChildren();
  (cards || []).forEach((card) => root.appendChild(userCard(card, badge)));
}

function fillNotes(notes) {
  const root = document.getElementById("notes");
  root.replaceChildren();
  (notes || []).forEach((note) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${esc(note.place_name)}</strong>${esc(note.note || "")}`;
    root.appendChild(li);
  });
}

function fillPicks(examples) {
  const root = document.getElementById("picks");
  root.replaceChildren();
  [
    ["나눠 먹기", examples.platter],
    ["타코", examples.taco],
    ["브리또", examples.burrito],
  ].forEach(([label, card]) => {
    if (!card) return;
    root.appendChild(userCard(card, `선택 조건: ${label} · 사진 확보 전`));
  });
}

async function main() {
  const meta = document.getElementById("meta");
  try {
    const res = await fetch("/v1/review/songdo");
    if (!res.ok) throw new Error(`검수 API ${res.status}`);
    const data = await res.json();
    const a = data.anchor || {};
    meta.textContent = `도보 기준 ${a.lat}, ${a.lng} · ${a.label || ""} · 1분≈${a.walk_m_per_min || 80}m · 엔진 연결 ${data.wired_to_ranking ? "됨" : "안 함"}`;
    fill("users", data.user_cards);
    fill("pack", data.pack, "첫 묶음 · 사진 확보 전");
    fill("menus", data.branch_menus, "같은 매장 검증 메뉴 · 사진 확보 전");
    fillPicks(data.pick_examples || {});
    fillNotes(data.investigation_notes || []);
  } catch (err) {
    meta.className = "meta err";
    meta.textContent = err.message || "검수 결과를 불러오지 못했습니다. 로컬 서버의 /v1/review/songdo가 필요합니다.";
  }
}

main();
