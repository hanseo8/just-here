/* Load the provider only after an explicit consented request. Server owns verification. */
(function(){
  let busy=false, resumed=false, sdkPromise=null, latestInfo=null;
  const key='jh_reward_identity_pending';
  function message(text){const el=document.getElementById('identity-message');el.textContent=text;window.JustHereMy?.open('reward-identity');el.tabIndex=-1;el.focus();}
  function pending(){try{return JSON.parse(localStorage.getItem(key)||'null')}catch(_){return null;}}
  function sdk(){
    if(window.PortOne)return Promise.resolve(window.PortOne);
    if(sdkPromise)return sdkPromise;
    sdkPromise=new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src='https://cdn.portone.io/v2/browser-sdk.js';
      const timer=setTimeout(()=>reject(Error('provider_load_failed')),15000);
      script.onload=()=>{clearTimeout(timer);window.PortOne?resolve(window.PortOne):reject(Error('provider_load_failed'));};
      script.onerror=()=>{clearTimeout(timer);reject(Error('provider_load_failed'));};document.head.append(script);
    }).catch(e=>{sdkPromise=null;throw e;});return sdkPromise;
  }
  async function finish(p){
    if(p.uid!==window.JustHereAuth.getUid()||p.expires<Date.now())throw Error('phone_identity_expired');
    const result=await jsonApi('/v1/rewards/identity/complete',{method:'POST',body:JSON.stringify({uid:p.uid,identity_verification_id:p.id})});
    window.JustHereAuth.setIdentity(result.uid,'phone',result.guest_token);currentUid=result.uid;
    localStorage.removeItem(key);history.replaceState(null,'',location.pathname+'#reward-identity');
    message('휴대폰 본인인증이 완료됐어요. 아래에서 보상 참여를 신청해 주세요.');await start();
  }
  const errors={phone_identity_not_configured:'휴대폰 본인인증 연동 준비 중이에요. 인증과 보상 신청은 아직 열리지 않았어요.',phone_identity_expired:'인증 시간이 지났거나 계정이 바뀌었어요. 다시 인증해 주세요.',phone_identity_account_conflict:'기존 계정 기록을 자동 연결할 수 없어요. 고객센터로 문의해 주세요.',phone_identity_di_unavailable:'중복 참여 확인 정보를 받지 못했어요. 고객센터로 문의해 주세요.',phone_identity_rate_limited:'인증 요청이 많아요. 잠시 후 다시 시도해 주세요.'};
  window.renderRewardIdentity=function(data={}){
    const info=data.identity||{required:true,configured:false,verified:false};latestInfo=info;
    const section=document.getElementById('reward-identity');section.hidden=info.required===false;
    const button=document.getElementById('verify-reward-identity');
    document.getElementById('identity-state').textContent=info.verified?'본인인증 완료 · 같은 사람의 중복 보상 참여를 제한해요.':info.configured?'음식 추천은 로그인 없이, 보상 참여 때만 본인인증해요.':'휴대폰 본인인증 연동 준비 중이에요. 음식 추천은 계속 이용할 수 있어요.';
    document.getElementById('identity-consent-label').hidden=info.verified||!info.configured;
    const summary=document.getElementById('my-participation-state');if(summary)summary.textContent=info.verified?'본인인증 완료':info.configured?'휴대폰 본인인증 후 참여':'본인인증 연동 준비 중';
    button.hidden=info.verified;button.disabled=busy;button.textContent=info.configured?'휴대폰 본인인증하기':'연동 준비 안내 보기';
    button.onclick=async()=>{
      if(busy)return;
      if(!info.configured){message(errors.phone_identity_not_configured);return;}
      if(window.JustHereNative&&!window.JustHereNative.verifyRewardIdentity){message('앱 업데이트가 필요해요. 최신 테스트 앱을 설치한 뒤 다시 시도해 주세요.');return;}
      if(!document.getElementById('identity-consent').checked){message('본인인증 안내를 확인하고 동의해 주세요.');return;}
      busy=true;button.disabled=true;button.textContent='인증창 연결 중…';
      try{
        const restored=await window.JustHereNative?.resumeRewardIdentity?.();
        if(restored){await finish(restored);return;}
        const provider=window.JustHereNative?null:await sdk();
        const uid=window.JustHereAuth.getUid();const request=await jsonApi('/v1/rewards/identity/start',{method:'POST',body:JSON.stringify({uid,consent:true})});
        const p={id:request.identityVerificationId,uid,expires:request.expires_at*1000};localStorage.setItem(key,JSON.stringify(p));
        if(window.JustHereNative){const returned=await window.JustHereNative.verifyRewardIdentity(request);await finish(returned);return;}
        const result=await provider.requestIdentityVerification({storeId:request.storeId,channelKey:request.channelKey,identityVerificationId:p.id,redirectUrl:location.origin+'/my#reward-identity'});
        if(result?.code){localStorage.removeItem(key);throw Error('provider_cancelled');}
        if(result)await finish(p);
      }catch(e){message(errors[e.message]||'인증을 완료하지 못했어요. 취소 또는 연결 상태를 확인하고 다시 시도해 주세요.');}
      finally{busy=false;button.disabled=false;button.textContent='휴대폰 본인인증하기';}
    };
    if(window.JustHereNative?.resumeRewardIdentity&&info.configured&&!info.verified&&!busy){resumeNative();}
    const id=new URLSearchParams(location.search).get('identityVerificationId');const p=pending();
    if(!window.JustHereNative&&!resumed&&id&&p&&p.id===id){resumed=true;busy=true;button.disabled=true;finish(p).catch(e=>message(errors[e.message]||'인증 결과를 확인하지 못했어요. 다시 시도해 주세요.')).finally(()=>{busy=false;button.disabled=false;});}
  };
  async function resumeNative(){
    if(busy||!latestInfo?.configured||latestInfo.verified)return;
    busy=true;const button=document.getElementById('verify-reward-identity');button.disabled=true;
    try{const p=await window.JustHereNative?.resumeRewardIdentity?.();if(p)await finish(p);}
    catch(e){message(errors[e.message]||'인증 결과를 확인하지 못했어요. 다시 시도하면 결과 확인을 재개해요.');}
    finally{busy=false;button.disabled=false;}
  }
  window.addEventListener('rewardIdentityReturn',()=>{resumeNative();});
})();
