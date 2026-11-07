const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const scope={Date,Number,AbortController,setTimeout,clearTimeout};vm.runInNewContext(fs.readFileSync('web/receipt-flow.js','utf8'),scope);
const flow=scope.JustHereReceiptFlow;
const tick=()=>new Promise(r=>setImmediate(r));
function fixture(){
 const fields=new Map([['image',{size:1000,type:'image/jpeg'}],['purchased_at','2026-11-07T12:00']]);
 const form={id:'original-form'},event={currentTarget:form,preventDefault(){}};let uid='owner',calls=0,success=0,mode='ok',resolve,refreshes=0;
 const states=[];
 const submit=flow.makeSubmitter({getIdentity:()=>({uid,token:'private-token'}),makeFormData:()=>({get:k=>fields.get(k),set:(k,v)=>fields.set(k,v)}),transport:async(url,options)=>{
   calls++;assert.equal(url,'/v1/rewards/receipts');assert.equal(options.headers['X-Guest-Token'],'private-token');
   if(mode==='network')throw Error('offline');
   if(mode==='wait')return new Promise(r=>resolve=r);
   if(mode==='timeout')return new Promise((r,j)=>options.signal.addEventListener('abort',()=>j(Error('aborted'))));
   return {ok:mode==='ok',status:mode==='ok'?200:400,json:async()=>mode==='ok'?{receipt:{id:'rcp-test'}}:{detail:mode}};
 },refresh:async()=>{refreshes++},onSuccess:f=>{assert.equal(f,form);success++},setState:(busy,text)=>states.push({busy,text}),timeoutMs:30});
 return {submit,event,fields,states,get calls(){return calls},get success(){return success},get refreshes(){return refreshes},set mode(v){mode=v},set uid(v){uid=v},respond:()=>resolve({ok:true,json:async()=>({receipt:{id:'rcp-test'}})})};
}
(async()=>{
 const missing=fixture();missing.fields.delete('image');await missing.submit(missing.event);assert.equal(missing.calls,0);assert(missing.states[0].text.includes('사진'));
 const invalid=fixture();invalid.fields.set('purchased_at','bad');await invalid.submit(invalid.event);assert.equal(invalid.calls,0);assert(invalid.states[0].text.includes('결제일'));
 const waiting=fixture();waiting.mode='wait';const first=waiting.submit(waiting.event);waiting.event.currentTarget=null;await waiting.submit(waiting.event);assert.equal(waiting.calls,1);waiting.respond();await first;assert.equal(waiting.success,1);assert.equal(waiting.refreshes,1);assert.equal(waiting.states.at(-1).busy,false);assert(waiting.states.some(x=>x.text?.includes('검토 중')));
 for(const mode of ['daily_limit_reached','duplicate_or_daily_limit','phone_identity_required','network','timeout']){
  const f=fixture();f.mode=mode;await f.submit(f.event);assert.equal(f.success,0);assert.equal(f.states.at(-1).busy,false);assert(f.states.some(x=>x.text&&(x.text.includes('3건')||x.text.includes('영수증')||x.text.includes('본인인증'))));
 }
 const changed=fixture();changed.mode='wait';const response=changed.submit(changed.event);changed.uid='other';changed.respond();await response;assert.equal(changed.success,0);assert.equal(changed.refreshes,0);assert(changed.states.some(x=>x.text?.includes('계정')));
 const receipt={id:'rcp-test',status:'approved',reward_points:300};assert(flow.receiptStatus(receipt).includes('신청 전'));assert(!flow.receiptStatus(receipt).includes('지급 완료'));
 assert(flow.receiptStatus({...receipt,status:'rejected'}).includes('적립되지'));
 assert(flow.receiptStatus(receipt,[{receipt_id:receipt.id,status:'pending'}]).includes('아직 송금되지'));
 assert(flow.receiptStatus(receipt,[{receipt_id:receipt.id,status:'processing'}]).includes('확인 중'));
 assert(flow.receiptStatus(receipt,[{receipt_id:receipt.id,status:'rejected'}]).includes('포인트 반환'));
 assert(flow.receiptStatus(receipt,[{receipt_id:receipt.id,status:'rejected'},{receipt_id:receipt.id,status:'paid'}]).includes('지급 완료'));
 console.log('PASS receipt UI: file/date validation, visible pending, double tap single upload, event target lifetime, specific failures, uncertain timeout retains form, account switch and distinct receipt/payment states');
})().catch(e=>{console.error(e);process.exitCode=1});
