/* Bank details stay in the form until submission; never put them in browser storage. */
(async function () {
  const form = document.getElementById('bank-form');
  const message = document.getElementById('bank-message');
  const history = document.getElementById('bank-history');
  let key = crypto.randomUUID();
  let keyReceipt = '';
  const labels = {pending:'지급 대기',processing:'송금 확인 중',paid:'300원 지급 완료',rejected:'반려 · 300P 반환'};
  async function refresh() {
    const uid = window.JustHereAuth.getUid();
    const data = await jsonApi('/v1/rewards/me?uid=' + encodeURIComponent(uid));
    const active = new Set((data.payouts || []).filter(p => p.status !== 'rejected').map(p => p.receipt_id));
    const eligible = (data.receipts || []).filter(r => r.status === 'approved' && !active.has(r.id));
    document.getElementById('bank-payout').hidden = !data.payout_config?.enabled || !eligible.length || !uid.startsWith('kakao_');
    if (data.payout_config?.enabled && eligible.length && !uid.startsWith('kakao_')) message.textContent = '지급 신청 전에 가게 선택 완료 화면에서 카카오 계정을 연결해 주세요.';
    const select = document.getElementById('bank-receipt');
    select.replaceChildren(...eligible.map(r => new Option(r.place_name + ' · 300원', r.id)));
    history.replaceChildren(...(data.payouts || []).map(p => {
      const el = document.createElement('article'); el.className = 'reward-item';
      el.textContent = `${labels[p.status] || p.status} · 계좌 끝 ${p.account_tail}${p.reason ? ' · ' + p.reason : ''}`;
      return el;
    }));
  }
  form.onsubmit = async event => {
    event.preventDefault();
    const receipt = document.getElementById('bank-receipt').value;
    if (receipt !== keyReceipt) { key = crypto.randomUUID(); keyReceipt = receipt; }
    const fields = new FormData(form);
    const button = form.querySelector('button'); button.disabled = true;
    try {
      await jsonApi('/v1/rewards/payouts', {method:'POST', body:JSON.stringify({
        uid:window.JustHereAuth.getUid(),receipt_id:receipt,request_id:key,
        bank:fields.get('bank'),account:fields.get('account'),holder:fields.get('holder'),consent:fields.has('consent'),
      })});
      form.reset(); key = crypto.randomUUID(); keyReceipt = '';
      message.textContent = '300원 지급 신청을 접수했어요. 실제 송금 후 지급 완료로 표시됩니다.';
      await start(); await refresh();
    } catch (_) { message.textContent = '신청 결과를 확인하지 못했어요. 지급 내역을 새로고침해 확인하거나 같은 내용으로 다시 시도해 주세요.'; }
    finally { button.disabled = false; }
  };
  await start();
  try { await refresh(); } catch (_) { message.textContent = '지급 내역을 불러오지 못했어요.'; }
})();
