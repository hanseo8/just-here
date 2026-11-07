/* No authentication credentials are accepted here. This page only hosts the provider UI. */
(function(){
  const status=document.getElementById('state'),button=document.getElementById('begin'),back=document.getElementById('return');
  const validId=s=>typeof s==='string'&&/^jh-identity-[-_A-Za-z0-9]{20,64}$/.test(s);
  const validState=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
  const q=new URLSearchParams(location.search);
  function returnLink(id,state){back.href='justthis://identity-complete?attempt_id='+encodeURIComponent(id)+'&state='+encodeURIComponent(state);back.hidden=false}
  // Provider redirect is not proof of success, including when it carries an error code.
  if(q.has('identityVerificationId')){
    const id=q.get('identityVerificationId'),state=q.get('state');
    if(q.getAll('identityVerificationId').length!==1||q.getAll('state').length!==1||!validId(id)||!validState(state)){status.textContent='복귀 정보를 확인할 수 없어요. 원래 앱에서 다시 시도해 주세요.';return}
    returnLink(id,state);status.textContent=q.has('code')?'인증이 취소되었거나 완료되지 않았어요. 앱으로 돌아가 확인해 주세요.':'인증창 이용이 끝났어요. 앱으로 돌아가 결과를 확인해 주세요.';
    history.replaceState(null,'',location.pathname);return;
  }
  let c;try{c=JSON.parse(decodeURIComponent(location.hash.slice(1)))}catch{}
  if(!c||!validId(c.id)||!validState(c.state)||!Number.isFinite(c.expires)||c.expires<=Date.now()||c.expires>Date.now()+600000||typeof c.storeId!=='string'||typeof c.channelKey!=='string'){status.textContent='인증 요청이 없거나 만료됐어요. 원래 앱에서 다시 시작해 주세요.';return}
  history.replaceState(null,'',location.pathname);
  returnLink(c.id,c.state);button.hidden=false;status.textContent='아래 버튼을 누르면 인증기관 화면으로 이동해요.';
  button.onclick=async()=>{
    if(button.disabled)return;button.disabled=true;status.textContent='인증창을 여는 중이에요…';
    try{
      if(c.expires<=Date.now())throw Error('expired');
      if(!window.PortOne)await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://cdn.portone.io/v2/browser-sdk.js';const timer=setTimeout(()=>reject(Error('timeout')),15000);script.onload=()=>{clearTimeout(timer);resolve()};script.onerror=()=>{clearTimeout(timer);reject(Error('sdk'))};document.head.append(script)});
      if(!window.PortOne)throw Error('sdk');
      const redirectUrl='https://justthis.co.kr/static/identity-native.html?state='+encodeURIComponent(c.state);
      const result=await window.PortOne.requestIdentityVerification({storeId:c.storeId,channelKey:c.channelKey,identityVerificationId:c.id,redirectUrl,forceRedirect:true,windowType:{mobile:'REDIRECTION',pc:'REDIRECTION'}});
      if(result?.code)throw Error('provider');
      if(result)status.textContent='앱으로 돌아가 인증 결과를 확인해 주세요.';
    }catch(_){status.textContent='인증창을 열지 못했거나 인증이 완료되지 않았어요. 앱으로 돌아가 다시 시도해 주세요.'}
    finally{button.disabled=false}
  };
})();
