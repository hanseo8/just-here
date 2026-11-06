/* Server-owned cohort state; never accept client-supplied reward amounts. */
window.renderBetaProgress = function (data, wallet={}) {
  const panel = document.getElementById('beta-progress');
  panel.hidden = !data?.enrolled;
  document.getElementById('beta-apply').hidden=!!data?.enrolled;
  const applyButton=document.getElementById('beta-apply-button');
  applyButton.disabled=wallet.reward_config?.enabled!==true;
  document.getElementById('beta-apply-message').textContent=applyButton.disabled?'현재 새 신청 접수가 일시 중지되어 있어요. 기존 신청·지급 내역은 확인할 수 있어요.':'';
  applyButton.onclick=async()=>{applyButton.disabled=true;try{if(!window.JustHereAuth.getUid()?.startsWith('kakao_'))throw Error('카카오 계정 연결 후 신청해 주세요.');await jsonApi('/v1/rewards/beta/apply',{method:'POST',body:JSON.stringify({uid:window.JustHereAuth.getUid()})});document.getElementById('beta-apply-message').textContent='신청을 접수했어요. 선정 결과는 MY에서 확인해 주세요.';}catch(e){document.getElementById('beta-apply-message').textContent=e.message||'접수하지 못했어요.';}finally{applyButton.disabled=wallet.reward_config?.enabled!==true;}};
  if (panel.hidden) return;
  document.getElementById('beta-state').textContent = `영수증 승인 ${data.approved_receipts}건 / 기간 한도 ${data.receipt_limit}건 (참여비 조건 ${data.required_receipts}건) · 설문 ${data.survey_submitted ? '제출 완료' : '미제출'}${data.bonus_eligible ? ' · 참여비 지급 자격 충족' : ''}`;
  document.getElementById('beta-deadline').textContent = '참여 기한: ' + new Date(data.ends_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'});
  const payoutForm=document.getElementById('beta-payout-form');
  const active=(wallet.payouts||[]).some(p=>p.id.startsWith('bpay_')&&p.status!=='rejected');
  payoutForm.hidden=!data.bonus_eligible||!wallet.payout_config?.enabled||active;
  let payoutRequestId=crypto.randomUUID();
  payoutForm.onsubmit=async event=>{event.preventDefault();const b=payoutForm.querySelector('button');b.disabled=true;const fields=new FormData(payoutForm);try{await jsonApi('/v1/rewards/beta/payout',{method:'POST',body:JSON.stringify({uid:window.JustHereAuth.getUid(),request_id:payoutRequestId,bank:fields.get('bank'),account:fields.get('account'),holder:fields.get('holder'),consent:fields.has('consent')})});payoutForm.reset();document.getElementById('beta-payout-message').textContent='지급 신청을 접수했어요. 실제 송금 완료 후 내역에 표시돼요.';await start();}catch(_){document.getElementById('beta-payout-message').textContent='신청 결과를 확인하지 못했어요. 지급 내역을 확인한 뒤 다시 시도해 주세요.';}finally{b.disabled=false;}};
  const form = document.getElementById('beta-survey');
  form.hidden = data.survey_submitted;
  form.onsubmit = async event => {
    event.preventDefault();
    const button = form.querySelector('button'); button.disabled = true;
    try {
      const response = await jsonApi('/v1/rewards/beta/survey',{method:'POST',body:JSON.stringify({uid:window.JustHereAuth.getUid(),answer:new FormData(form).get('answer')})});
      await start();
    } catch (_) { document.getElementById('beta-message').textContent='제출하지 못했어요. 참여 기한과 연결 상태를 확인해 주세요.'; }
    finally { button.disabled=false; }
  };
};
