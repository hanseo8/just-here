(function () {
  const queue = document.getElementById('payout-queue');
  const message = document.getElementById('payout-message');
  const labels = {pending:'지급 대기',processing:'송금 확인 중',paid:'지급 완료',rejected:'반려'};
  function button(text, action) { const el = document.createElement('button'); el.textContent = text; el.onclick = action; return el; }
  async function reload() {
    queue.replaceChildren();
    try {
      const data = await call('/v1/admin/payouts');
      for (const p of data.payouts) {
        const box = document.createElement('article'); box.className = 'metric';
        const title = document.createElement('p');
        title.textContent = `${p.id} · 300원 · 계좌 끝 ${p.account_tail} · ${labels[p.status]}`;
        box.append(title);
        const details = document.createElement('p'); box.append(details);
        const reference = document.createElement('input'); reference.placeholder = '실제 송금 거래번호 (개인정보 제외)'; reference.maxLength = 100;
        const reason = document.createElement('input'); reason.placeholder = '반려 사유'; reason.maxLength = 240;
        const noTransfer = document.createElement('input'); noTransfer.type = 'checkbox'; noTransfer.style.minWidth = 'auto';
        const label = document.createElement('label'); label.append(noTransfer, document.createTextNode('실제 송금이 없음을 확인했습니다'));
        async function act(action) {
          try {
            await call('/v1/admin/payouts/' + encodeURIComponent(p.id) + '/decision', {method:'POST',body:JSON.stringify({action,reference:reference.value,reason:reason.value,no_transfer:noTransfer.checked})});
            message.textContent = '지급 상태를 기록했습니다.'; await reload();
          } catch (_) { message.textContent = '처리하지 못했습니다. 현재 상태·거래번호·미송금 확인을 점검하세요.'; }
        }
        if (p.status === 'pending') box.append(button('처리 시작', () => act('processing')));
        if (p.status === 'processing') {
          box.append(button('송금 계좌 확인', async () => {
            try { const r = await call('/v1/admin/payouts/' + encodeURIComponent(p.id) + '/recipient', {method:'POST'}); details.textContent = `${r.bank} / ${r.account} / ${r.holder}`; }
            catch (_) { message.textContent = '계좌를 확인하지 못했습니다.'; }
          }), reference, button('실제 송금 완료 기록', () => act('paid')));
        }
        if (['pending','processing'].includes(p.status)) box.append(reason, label, button('반려 및 300P 반환', () => act('rejected')));
        queue.append(box);
      }
      if (!data.payouts.length) queue.textContent = '지급 신청이 없습니다.';
    } catch (_) { message.textContent = '지급 목록을 불러오지 못했습니다.'; }
  }
  document.getElementById('load').addEventListener('click', reload);
})();
