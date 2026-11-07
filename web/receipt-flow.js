/* Receipt approval credits points; payout records alone describe settlement. */
(function(root){
  const errors={
    duplicate_or_daily_limit:'같은 영수증이나 이미 접수한 식사인지 확인해 주세요. 내 영수증 내역도 확인해 주세요.',
    daily_limit_reached:'한국시간 결제일 기준 하루 최대 3건까지 접수할 수 있어요.',
    phone_identity_required:'보상 참여 전 휴대폰 본인인증을 완료해 주세요.',
    beta_outside_period:'선정된 테스트 참여 기간 안에 이용한 식사만 접수할 수 있어요.',
    beta_receipt_limit_reached:'이번 테스트의 영수증 접수 한도에 도달했어요.',
    beta_selection_before_enrollment:'테스트 선정 후 선택한 가게의 영수증을 올려 주세요.',
    ineligible_attribution:'앱에서 방문할 가게를 선택한 식사 기록이 필요해요.',
    unsupported_image_type:'JPG, PNG, WEBP 사진을 선택해 주세요.',
    invalid_image_content:'정상적인 영수증 사진 파일을 다시 선택해 주세요.',
    invalid_image_size:'영수증 사진은 8MB 이하로 선택해 주세요.',
    purchase_time_out_of_range:'결제일을 확인해 주세요. 최근 3일 이내의 실제 결제 시간을 입력해 주세요.',
    purchase_before_selection:'가게를 선택한 후 이용한 식사의 영수증을 올려 주세요.',
    attribution_expired:'이 식사의 인증 가능 기간이 지났어요. 다른 식사 기록을 확인해 주세요.',
    approval_number_required:'영수증 승인번호를 6자 이상 입력해 주세요.',
    invalid_amount:'영수증 결제 금액을 확인해 주세요.',
    pilot_capacity_reached:'현재 모집 예산 또는 접수 한도에 도달했어요.',
    pilot_ended:'현재 영수증 접수가 닫혀 있어요. 기존 접수 내역은 확인할 수 있어요.',
  };
  function errorText(code,status){return errors[code]||(status===401?'계정 확인이 필요해요. MY를 새로고침한 후 다시 시도해 주세요.':status===503?'영수증 접수가 일시 중지됐어요. 잠시 후 다시 확인해 주세요.':'접수 결과를 확인하지 못했어요. 내 영수증 내역을 먼저 새로고침해 확인해 주세요. 입력한 내용은 유지했어요.');}
  function receiptStatus(r,payouts=[]){
    if(r.status==='pending')return '검토 중 · 승인 전에는 사용할 수 없어요.';
    if(r.status==='rejected')return '영수증 반려 · 적립되지 않았어요.';
    if(r.status!=='approved')return '상태를 확인해 주세요.';
    const active=payouts.find(p=>p.receipt_id===r.id&&p.status!=='rejected');
    const rejected=payouts.some(p=>p.receipt_id===r.id&&p.status==='rejected');
    const labels={pending:'지급 신청 접수 · 아직 송금되지 않았어요.',processing:'송금 확인 중 · 완료 내역을 확인해 주세요.',paid:'지급 완료 · 관리자 송금 확인 처리됨'};
    return active?(labels[active.status]||'지급 상태 확인 필요'):rejected?'지급 신청 반려 · 포인트 반환, 지급 내역의 사유를 확인해 다시 신청해 주세요.':Number(r.reward_points||0)+'P 적립 완료 · 계좌 지급 신청 전이에요.';
  }
  function makeSubmitter({getIdentity,transport,refresh,setState,onSuccess,makeFormData=form=>new FormData(form),timeoutMs=45000}){
    let busy=false;
    return async function(event){
      event.preventDefault();if(busy)return;
      const form=event.currentTarget,data=makeFormData(form),identity=getIdentity(),image=data.get('image');
      if(!identity?.uid||!identity.token){setState(false,'계정 확인 후 다시 시도해 주세요.');return;}
      if(!image||!image.size){setState(false,'영수증 사진을 먼저 선택해 주세요.');return;}
      if(image.size>8*1024*1024){setState(false,errors.invalid_image_size);return;}
      if(!['image/jpeg','image/png','image/webp'].includes(image.type)){setState(false,errors.unsupported_image_type);return;}
      const when=new Date(String(data.get('purchased_at')||''));
      if(!Number.isFinite(when.getTime())){setState(false,'영수증 결제일과 시간을 입력해 주세요.');return;}
      data.set('purchased_at',when.toISOString());data.set('uid',identity.uid);data.set('review_tags','');data.set('photo_reuse_consent','false');
      busy=true;setState(true,'영수증을 전송하고 있어요. 완료될 때까지 기다려 주세요.');
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
      try{
        const res=await transport('/v1/rewards/receipts',{method:'POST',headers:{'X-Guest-Token':identity.token},body:data,signal:controller.signal});
        const body=await res.json().catch(()=>({}));
        if(getIdentity()?.uid!==identity.uid){setState(true,'계정이 바뀌었어요. 현재 계정의 내역을 새로 확인해 주세요.');return;}
        if(!res.ok){setState(true,errorText(typeof body.detail==='string'?body.detail:'',res.status));return;}
        if(!body.receipt?.id)throw Error('unknown_result');
        onSuccess(form);
        setState(true,'영수증이 접수됐어요. 현재 검토 중이며 승인 후 포인트가 적립돼요.');
        try{await refresh()}catch(_){setState(true,'영수증은 접수됐어요. 내역을 새로고침해 검토 상태를 확인해 주세요.');}
      }catch(_){setState(true,errorText());}
      finally{clearTimeout(timer);busy=false;setState(false);}
    };
  }
  root.JustHereReceiptFlow={receiptStatus,errorText,makeSubmitter};
})(typeof window!=='undefined'?window:globalThis);
