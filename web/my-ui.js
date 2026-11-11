/* MY navigation only opens presentation folds; it never changes participation eligibility. */
(function(){
  function open(id){
    const target=document.getElementById(id);if(!target||target.hidden)return false;
    if(target.tagName==='DETAILS')target.open=true;
    for(let parent=target.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    target.scrollIntoView({behavior:'smooth',block:'start'});return true;
  }
  function renderTitles(rows){
    const list=document.getElementById('my-title-list');list.replaceChildren();
    const latest=rows[rows.length-1];const image=document.getElementById('my-title-image');
    document.getElementById('my-title-name').textContent=latest?.title||'첫 칭호를 만나볼까요?';
    document.getElementById('my-title-description').textContent=latest?.sub_text||'가게를 고르면 나의 음식 취향 칭호가 쌓여요.';
    document.getElementById('my-title-count').textContent=rows.length?'모은 칭호 '+rows.length+'개':'아직 받은 칭호가 없어요';
    document.getElementById('my-title-collection').hidden=!rows.length;
    image.hidden=true;image.removeAttribute('src');
    if(latest?.id&&/^[a-z_]+$/.test(latest.id)){image.src='/static/badges/'+latest.id+'.png?v=20260930-badges1';image.hidden=false;image.onerror=()=>{image.hidden=true;};}
    for(const row of rows){const card=document.createElement('div');card.className='my-title-chip';const name=document.createElement('strong');name.textContent=row.title;card.append(name);list.append(card);}
  }
  function nextAction(data, available=false) {
    const action=(label,message,target,step)=>({label,message,target,step});
    if(!data)return action('다시 불러오기','연결 상태를 확인하지 못했어요. 다시 불러와 주세요.','retry',-1);
    if(data.reward_config?.enabled!==true)return action('기존 영수증 내역 보기','현재 새 접수는 쉬고 있어요. 기존 검토·지급 내역은 확인할 수 있어요.','activity',-1);
    if(data.identity?.required!==false&&!data.identity?.verified){
      if(data.identity?.configured!==true)return action('인증 오픈 안내 보기','본인인증 연결을 준비 중이에요. 지금은 음식 추천을 먼저 이용해 주세요.','reward-identity',0);
      return action('휴대폰 본인인증하기','보상 참여 전 최초 본인인증이 필요해요.','reward-identity',0);
    }
    if(!data.beta?.enrolled&&data.pilot?.claim_limit===0){
      if(data.beta_application?.applied===true)return action('선정 결과 확인','신청이 접수됐어요. 선정 전에는 보상 영수증을 올릴 수 없어요.','beta-apply',2);
      return action('베타 참여 신청하기','참여 조건을 확인하고 신청해 주세요. 운영자 선정 후 참여할 수 있어요.','beta-apply',1);
    }
    if(available)return action('영수증 사진 업로드','선택한 식당에서 식사하셨나요? 결제 영수증과 솔직한 후기를 남겨 주세요.','claim',3);
    if((data.payouts||[]).some(p=>['pending','processing'].includes(p.status)))return action('지급 상태 확인','지급 신청을 확인 중이에요. 신청은 송금 완료와 달라요.','my-settlement',4);
    if((data.receipts||[]).some(r=>r.status==='pending'))return action('영수증 검토 상태 확인','접수한 영수증을 검토 중이에요. 결과는 내 영수증에서 확인해 주세요.','activity',4);
    if((data.balance||0)>0)return action('보상 지급 안내 보기','승인된 포인트가 있어요. 지급 가능한 영수증과 조건을 확인해 주세요.','my-settlement',4);
    return action('가게 먼저 고르기','가게를 추천받고 선택한 뒤 식사 후 영수증을 올려 주세요.','home',3);
  }
  function renderNext(data,available){
    const next=nextAction(data,available);
    document.getElementById('my-next-title').textContent=next.label;
    document.getElementById('my-next-copy').textContent=next.message;
    const steps=document.getElementById('my-next-steps');steps.replaceChildren();
    ['본인인증','참여 신청','선정','식사·영수증','검토·지급'].forEach((name,index)=>{
      const item=document.createElement('li');item.textContent=name;
      if(index===next.step)item.setAttribute('aria-current','step');
      steps.append(item);
    });
    document.getElementById('my-next-action').textContent=next.label;
    document.getElementById('my-next-action').onclick=()=>document.getElementById('open-receipt-upload').click();
    return next;
  }
  window.JustHereMy={open,renderTitles,nextAction,renderNext};
  window.addEventListener('hashchange',()=>open(location.hash.slice(1)));
  window.addEventListener('DOMContentLoaded',()=>{if(location.hash)open(location.hash.slice(1));});
})();
