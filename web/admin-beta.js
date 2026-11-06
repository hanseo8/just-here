(function(){
  const list=document.getElementById('beta-roster'), message=document.getElementById('beta-admin-message');
  async function loadBeta(){
    try{
      const data=await call('/v1/admin/rewards/beta');
      message.textContent=`선정 ${data.selected}/${data.capacity}명 · 최대 예약 ${data.reserved_max_krw.toLocaleString()}원 / 예산 ${data.budget_max_krw.toLocaleString()}원`;
      list.replaceChildren();
      for(const person of data.applications){
        const row=document.createElement('p'),label=document.createElement('span'),button=document.createElement('button');
        label.textContent=person.uid+' · 신청 '+new Date(person.created_at).toLocaleString('ko-KR');
        button.textContent='선정·17,600원 예산 예약';button.disabled=data.selected>=data.capacity;
        button.onclick=async()=>{button.disabled=true;try{await call('/v1/admin/rewards/beta/enroll',{method:'POST',body:JSON.stringify({uid:person.uid})});await loadBeta();}catch(_){message.textContent='선정하지 못했습니다. 계정·정원·모집 활성 상태를 확인하세요.';button.disabled=false;}};
        row.append(label,button);list.append(row);
      }
      for(const member of data.members){const row=document.createElement('p');row.textContent=`선정 ${member.uid} · 기한 ${new Date(member.ends_at).toLocaleString('ko-KR')} · 설문 ${member.survey_at?'완료':'미제출'}`;list.append(row);}
    }catch(_){message.textContent='베타 명단을 불러오지 못했습니다. 관리자 인증을 확인하세요.';}
  }
  document.getElementById('load').addEventListener('click',loadBeta);
})();
