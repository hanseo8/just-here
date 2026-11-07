/* Bank details stay in the form until submission; never put them in browser storage. */
(async function () {
  const form = document.getElementById('bank-form');
  const message = document.getElementById('bank-message');
  const history = document.getElementById('bank-history');
  let key = crypto.randomUUID();
  let keyReceipt = '';
  let busy = false;
  const labels = {pending:'지급 대기',processing:'송금 확인 중',paid:'지급 완료',rejected:'반려 · 포인트 반환'};
  function refresh(data) {
    const uid = window.JustHereAuth.getUid();
    if (!data) return;
    const active = new Set((data.payouts || []).filter(p => p.status !== 'rejected').map(p => p.receipt_id));
    const eligible = (data.receipts || []).filter(r => r.status === 'approved' && !active.has(r.id));
    document.getElementById('bank-payout').hidden = !data.payout_config?.enabled || !eligible.length || (data.identity?.required!==false?!data.identity?.verified:!uid.startsWith('kakao_'));
    if (data.payout_config?.enabled && eligible.length && (data.identity?.required!==false?!data.identity?.verified:!uid.startsWith('kakao_'))) message.textContent = '지급 신청 전에 휴대폰 본인인증을 완료해 주세요.';
    if (!data.payout_config?.enabled) message.textContent=' 계좌 지급은 현재 열려 있지 않아요. 기존 지급 내역은 계속 확인할 수 있어요.';
    if(data.payout_config?.enabled&&(!eligible.length||data.identity?.verified||data.identity?.required===false))message.textContent='';
    const select = document.getElementById('bank-receipt');
    const previous=select.value;
    select.replaceChildren(...eligible.map(r => new Option(r.place_name + ' · ' + Number(r.reward_points) + '원', r.id)));
    if(eligible.some(r=>r.id===previous))select.value=previous;
    const updateAmount=()=>{const r=eligible.find(x=>x.id===select.value);const amount=Number(r?.reward_points||data.payout_config?.amount_krw||100);form.querySelector('button').textContent=amount+'원 계좌 지급 신청';document.getElementById('bank-amount-terms').textContent=amount+'원 송금을 위한 은행·계좌번호·예금주 수집에 동의합니다.';};select.onchange=updateAmount;updateAmount();
    history.replaceChildren(...(data.payouts || []).map(p => {
      const el = document.createElement('article'); el.className = 'reward-item';
      el.textContent = `${Number(p.amount_krw)}원 · ${labels[p.status] || p.status} · 계좌 끝 ${p.account_tail}${p.reason ? ' · ' + p.reason : ''}`;
      return el;
    }));
  }
  form.onsubmit = async event => {
    event.preventDefault();
    if(busy)return;
    const uid=window.JustHereAuth.getUid();
    const receipt = document.getElementById('bank-receipt').value;
    if(!receipt){message.textContent='지급 신청할 승인 영수증을 선택해 주세요.';return;}
    if (receipt !== keyReceipt) { key = crypto.randomUUID(); keyReceipt = receipt; }
    const fields = new FormData(form);
    const button = form.querySelector('button'); button.disabled = true;busy=true;form.setAttribute('aria-busy','true');message.textContent='지급 신청을 접수하고 있어요. 아직 송금된 상태가 아니에요.';
    try {
      await jsonApi('/v1/rewards/payouts', {method:'POST', body:JSON.stringify({
        uid,receipt_id:receipt,request_id:key,
        bank:fields.get('bank'),account:fields.get('account'),holder:fields.get('holder'),consent:fields.has('consent'),
      })});
      form.reset(); key = crypto.randomUUID(); keyReceipt = '';
      if(window.JustHereAuth.getUid()!==uid){message.textContent='계정이 바뀌었어요. 현재 계정의 지급 내역을 다시 확인해 주세요.';return;}
      await refresh(await start());
      message.textContent = '지급 신청을 접수했어요. 실제 송금 후 지급 완료로 표시됩니다.';
    } catch (_) { message.textContent = '신청 결과를 확인하지 못했어요. 지급 내역을 새로고침해 확인하거나 같은 내용으로 다시 시도해 주세요.'; }
    finally { button.disabled = false;busy=false;form.setAttribute('aria-busy','false'); }
  };
  window.renderRewardPayouts=refresh;
  try { await start(); } catch (err) { message.textContent = String(err.message||'').includes('disabled') ? '계좌 지급은 모집 시작 후 안내됩니다.' : '지급 내역을 불러오지 못했어요.'; }
})();
