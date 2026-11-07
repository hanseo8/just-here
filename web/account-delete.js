/* Intake is never completion. A scoped receipt can show progress after login revocation. */
(function(){
 const get=id=>document.getElementById(id),form=get('deletion-form'),button=get('submit'),message=get('status');
 const withdraw=get('withdraw'),refresh=get('refresh-deletion');let busy=false;
 const trackingKey='jh_deletion_receipt';
 function tracking(){try{return JSON.parse(localStorage.getItem(trackingKey)||'null')}catch(_){return null}}
 function saveTracking(value,uid){if(value?.receipt&&value.request_id){try{localStorage.setItem(trackingKey,JSON.stringify({...value,uid}))}catch(_){}}}
 function render(row){
  get('deletion-progress').hidden=!row;
  if(!row){form.hidden=false;button.disabled=false;withdraw.hidden=true;message.textContent='현재 계정의 삭제 요청이 없어요. 아래에서 삭제 검토를 요청할 수 있어요.';return;}
  const inactive=row.status==='withdrawn',removed=row.status==='active_data_deleted',processing=row.status==='deleting';form.hidden=!inactive;button.disabled=!inactive;withdraw.hidden=!['requested','reviewing'].includes(row.status);
  message.textContent=removed?'활성 계정과 이용 기록을 삭제했어요. 백업 정리는 대기 중이며 전체 삭제 완료 상태는 아니에요.':processing?'계정 삭제를 처리 중이에요. 처리가 끝나기 전에는 완료로 표시하지 않아요.':inactive?'삭제 요청을 철회했어요. 기존 계정과 기록은 유지됩니다.':row.status==='reviewing'?'관리자가 삭제 범위를 검토하고 있어요. 아직 삭제 완료 상태가 아니에요.':'삭제 검토 요청을 접수했어요. 아직 계정이나 기록이 삭제되지는 않았어요.';
  const saved=tracking();
  if(removed&&saved?.request_id===row.id&&saved.uid===JustHereAuth.getUid()){
    for(const key of ['jh_uid','jh_guest_token','jh_auth_type','jh_device_id'])localStorage.removeItem(key);
    for(const key of ['jh_reward_identity_pending','jh_native_kakao_attempt']){try{if(JSON.parse(localStorage.getItem(key)||'null')?.uid===saved.uid)localStorage.removeItem(key)}catch(_){}}
  }
  get('deletion-request-id').textContent='접수번호: '+row.id;
  const date=new Date(row.updated_at);get('deletion-updated-at').textContent=Number.isFinite(date.getTime())?'최근 변경: '+date.toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'';
  get('deletion-reasons').replaceChildren(...(inactive?[]:row.reasons||[]).map(text=>{const li=document.createElement('li');li.textContent=text;return li}));
  get('deletion-next-action').textContent=removed?'이 화면의 상태 확인용 접수증으로 백업 정리 진행 상황을 확인할 수 있어요. 접수증은 읽기 전용이며 다른 사람에게 공유하지 마세요.':inactive?'다시 요청하려면 아래 동의 항목을 확인해 주세요.':row.next_action||'삭제 범위와 처리 결과는 고객센터에서 안내합니다.';
 }
 async function trackedStatus(){
  const saved=tracking(),uid=JustHereAuth.getUid();
  if(!saved?.receipt||(uid&&uid!==saved.uid))throw Error('identity');
  const response=await fetch('/v1/me/deletion/status',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:saved.request_id,receipt:saved.receipt})});
  if(uid!==JustHereAuth.getUid())throw Error('account_changed');
  if(!response.ok)throw Error('identity');return response.json();
 }
 async function call(method='GET',cancel=false){
  const uid=JustHereAuth.getUid(),token=JustHereAuth.getToken();if(!uid||!token){if(method==='GET')return trackedStatus();throw Error('identity');}
  const response=await fetch('/v1/me/deletion'+(cancel?'/withdraw':'')+(method==='GET'?'?uid='+encodeURIComponent(uid):''),{method,cache:'no-store',headers:{'Content-Type':'application/json','X-Guest-Token':token},...(method==='POST'?{body:JSON.stringify({uid,confirm:cancel||get('confirm').checked})}:{})});
  if(uid!==JustHereAuth.getUid())throw Error('account_changed');
  if(response.status===401&&method==='GET')return trackedStatus();
  if(!response.ok)throw Error(response.status===401?'identity':'request');const data=await response.json();saveTracking(data.tracking,uid);return data;
 }
 async function run(action){
  if(busy)return;busy=true;button.disabled=true;withdraw.disabled=true;refresh.disabled=true;form.setAttribute('aria-busy','true');
  try{if(action)await action();const data=await call();const saved=tracking();if(data.request&&JustHereAuth.getToken()&&(!saved||saved.uid!==JustHereAuth.getUid()||saved.request_id!==data.request.id)){
    const uid=JustHereAuth.getUid();const response=await fetch('/v1/me/deletion/receipt',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json','X-Guest-Token':JustHereAuth.getToken()},body:JSON.stringify({uid,confirm:true})});
    if(uid!==JustHereAuth.getUid())throw Error('account_changed');if(response.ok)saveTracking((await response.json()).tracking,uid);
   }render(data.request);}
  catch(e){message.textContent=e.message==='identity'||e.message==='account_changed'?'현재 계정을 확인하지 못했어요. MY에서 기존 계정 연결을 확인해 주세요.':'처리 결과를 확인하지 못했어요. 상태 새로고침으로 접수 여부를 먼저 확인해 주세요.';if(e.message==='identity'||e.message==='account_changed'){get('deletion-progress').hidden=true;form.hidden=true;withdraw.hidden=true;}}
  finally{busy=false;withdraw.disabled=false;refresh.disabled=false;button.disabled=form.hidden;form.setAttribute('aria-busy','false');}
 }
 refresh.onclick=()=>run();withdraw.onclick=()=>run(()=>call('POST',true));
 form.onsubmit=event=>{event.preventDefault();if(!get('confirm').checked){message.textContent='삭제 검토 요청 안내를 확인하고 동의해 주세요.';return;}return run(()=>call('POST'));};
 run();
})();
