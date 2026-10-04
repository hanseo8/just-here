(function () {
  const queue = document.getElementById('payout-queue');
  const message = document.getElementById('payout-message');
  const labels = {pending:'지급 대기',processing:'송금 확인 중',paid:'지급 완료',rejected:'반려'};
  function button(text, action) { const el = document.createElement('button'); el.textContent = text; el.onclick = action; return el; }
  async function reload() {
    queue.replaceChildren();
    const summary = document.getElementById('payout-summary');
    summary.replaceChildren();
    try {
      const data = await call('/v1/admin/payouts');
      if (data.reconciliation) {
        for (const [state, value] of Object.entries(data.reconciliation.states)) {
          const line = document.createElement('div'); line.className = 'payout-stat';
          const stateLabel = document.createElement('span'); stateLabel.textContent = labels[state];
          const amount = document.createElement('strong'); amount.textContent = `${value.count}건 · ${value.amount_krw.toLocaleString()}원`;
          line.append(stateLabel, amount);
          summary.append(line);
        }
        const check = document.createElement('p');
        check.className = 'payout-check' + (data.reconciliation.records_match ? '' : ' warning');
        check.textContent = data.reconciliation.records_match
          ? '앱 지급 기록과 포인트 장부가 일치합니다. 은행 거래내역은 별도로 확인하세요.'
          : `장부 불일치 ${data.reconciliation.mismatch_count}건: 추가 지급 전에 기록을 확인하세요.`;
        summary.append(check);
      }
      for (const p of data.payouts) {
        const box = document.createElement('article'); box.className = 'payout-item';
        const title = document.createElement('h3'); title.textContent = `300원 · ${labels[p.status]}`;
        const meta = document.createElement('p'); meta.className = 'muted';
        meta.textContent = `신청 ${new Date(p.created_at).toLocaleString('ko-KR')} · 계좌 끝 ${p.account_tail} · ${p.id.slice(-8)}`;
        const details = document.createElement('div'); details.className = 'payout-recipient'; details.hidden = true;
        box.append(title, meta, details);
        const reference = document.createElement('input'); reference.placeholder = '은행 거래내역의 고유 참조번호'; reference.maxLength = 100;
        const reason = document.createElement('input'); reason.placeholder = '반려 사유'; reason.maxLength = 240;
        const noTransfer = document.createElement('input'); noTransfer.type = 'checkbox';
        const label = document.createElement('label'); label.className = 'no-transfer'; label.append(noTransfer, document.createTextNode('은행 거래내역에서 실제 송금이 없음을 확인했습니다.'));
        async function act(action) {
          try {
            await call('/v1/admin/payouts/' + encodeURIComponent(p.id) + '/decision', {method:'POST',body:JSON.stringify({action,reference:reference.value,reason:reason.value,no_transfer:noTransfer.checked})});
            message.textContent = '지급 상태를 기록했습니다.'; await reload();
          } catch (_) { message.textContent = '처리하지 못했습니다. 현재 상태·거래번호·미송금 확인을 점검하세요.'; }
        }
        const actions = document.createElement('div'); actions.className = 'payout-actions';
        if (p.status === 'pending') actions.append(button('처리 시작', () => act('processing')));
        if (p.status === 'processing') {
          const paidButton = button('실제 송금 완료 기록', () => act('paid'));
          paidButton.disabled = true;
          const updatePaidButton = () => { paidButton.disabled = details.hidden || !reference.value.trim(); };
          reference.addEventListener('input', updatePaidButton);
          actions.append(button('송금 계좌 확인', async () => {
            try { const r = await call('/v1/admin/payouts/' + encodeURIComponent(p.id) + '/recipient', {method:'POST'}); details.textContent = `은행 ${r.bank} · 계좌 ${r.account} · 예금주 ${r.holder}`; details.hidden = false; updatePaidButton(); }
            catch (_) { message.textContent = '계좌를 확인하지 못했습니다.'; }
          }), paidButton);
          box.append(reference);
        }
        if (['pending','processing'].includes(p.status)) actions.append(button('반려 및 300P 반환', () => act('rejected')));
        box.append(actions);
        if (['pending','processing'].includes(p.status)) box.append(reason, label);
        queue.append(box);
      }
      if (!data.payouts.length) queue.textContent = '지급 신청이 없습니다.';
    } catch (_) { message.textContent = '지급 목록을 불러오지 못했습니다.'; }
  }
  document.getElementById('load').addEventListener('click', reload);
})();
