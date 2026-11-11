/* Server-owned cohort state; never accept client-supplied reward amounts. */
window.renderBetaProgress = function (data, wallet={}) {
  const panel = document.getElementById('beta-progress');
  panel.hidden = !data?.enrolled;
  document.getElementById('beta-apply').hidden=!!data?.enrolled;
  const applyButton=document.getElementById('beta-apply-button');
  const applyMessage=document.getElementById('beta-apply-message');
  const connectAction=document.getElementById('beta-connect-action');
  const applied=wallet.beta_application?.applied===true;
  const enabled=wallet.reward_config?.enabled===true;
  applyButton.disabled=false;
  applyButton.textContent=applied?'신청 접수 완료 · 상태 확인':enabled?'테스트 참여 신청':'모집 상태 확인';
  applyMessage.textContent=applied?'참여 신청을 접수했어요. 아직 선정 전이며, 선정 결과는 MY에서 확인해 주세요.':enabled?'신청 후 운영자가 선정해요. 신청만으로 참여·지급이 확정되지는 않아요.':'현재 새 신청 접수가 일시 중지되어 있어요. 기존 신청·지급 내역은 확인할 수 있어요.';
  const identityWaiting=wallet.identity?.required!==false&&!wallet.identity?.verified&&wallet.identity?.configured!==true;
  if(!applied&&enabled&&identityWaiting){applyButton.textContent='인증 오픈 안내 보기';applyMessage.textContent='본인인증 연결 준비 중이에요. 인증이 열리면 참여 신청을 진행할 수 있어요.';}
  if(connectAction)connectAction.hidden=true;
  const showMessage=text=>{window.JustHereMy?.open('beta-apply');applyMessage.textContent=text;applyMessage.tabIndex=-1;applyMessage.focus();};
  applyButton.onclick=async()=>{
    if(applied){showMessage('신청이 이미 접수됐어요. 선정 결과가 나오면 MY에 참여 기간이 표시돼요.');return;}
    if(!enabled){showMessage('지금은 참여 신청 접수가 중지되어 있어요. 접수가 열리면 이 버튼으로 신청할 수 있어요.');return;}
    if(identityWaiting){window.JustHereMy?.open('reward-identity');return;}
    const uid=window.JustHereAuth.getUid();
    if(wallet.identity?.required!==false&&!wallet.identity?.verified){
      if(connectAction)connectAction.hidden=false;
      showMessage('보상 참여에는 휴대폰 본인인증이 필요해요. 아래 ‘휴대폰 본인인증하기’를 눌러 주세요.');return;
    }
    applyButton.disabled=true;applyButton.textContent='신청 접수 중…';showMessage('참여 신청을 보내고 있어요. 잠시만 기다려 주세요.');
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
    try{
      await jsonApi('/v1/rewards/beta/apply',{method:'POST',signal:controller.signal,body:JSON.stringify({uid})});
      applyButton.textContent='신청 접수 완료';showMessage('참여 신청을 접수했어요. 아직 선정 전이며, 선정 결과는 MY에서 확인해 주세요.');
      applyButton.onclick=()=>showMessage('신청이 접수됐어요. 선정 결과는 MY에서 확인해 주세요.');
      await start();
    }catch(e){
      const errors={phone_identity_required:'휴대폰 본인인증 후 다시 신청해 주세요.',beta_capacity_reached:'현재 베타 선정 인원이 모두 찼어요.',beta_application_capacity_reached:'현재 신청 정원이 모두 찼어요.'};
      applyButton.textContent='참여 신청 다시 시도';
      showMessage(e.name==='AbortError'?'응답이 늦어지고 있어요. 새로고침해 접수 상태를 확인한 뒤 다시 시도해 주세요.':errors[e.message]||'신청 결과를 확인하지 못했어요. 새로고침해 접수 상태를 확인한 뒤 다시 시도해 주세요.');
    }finally{clearTimeout(timer);applyButton.disabled=false;}
  };
  if (panel.hidden) return;
  document.getElementById('beta-state').textContent = `영수증 승인 ${data.approved_receipts}건 / 기간 한도 ${data.receipt_limit}건 (참여비 조건 ${data.required_receipts}건) · 설문 ${data.survey_submitted ? '제출 완료' : '미제출'}${data.bonus_eligible ? ' · 참여비 지급 자격 충족' : ''}`;
  document.getElementById('beta-deadline').textContent = '참여 기한: ' + new Date(data.ends_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'});
  const payoutForm=document.getElementById('beta-payout-form');
  const active=(wallet.payouts||[]).some(p=>p.id.startsWith('bpay_')&&p.status!=='rejected');
  payoutForm.hidden=!data.bonus_eligible||!wallet.payout_config?.enabled||active||(wallet.identity?.required!==false&&!wallet.identity?.verified);
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
