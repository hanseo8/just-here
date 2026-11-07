const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('web/account-delete.js','utf8'),tick=()=>new Promise(r=>setImmediate(r));
function fixture(){
 const nodes={},memory=new Map([['jh_uid','owner'],['jh_guest_token','private-token'],['jh_device_id','own-device']]),calls=[];
 const get=id=>nodes[id]??={hidden:false,checked:false,disabled:false,textContent:'',setAttribute(){},replaceChildren(...children){this.children=children}};
 let row=null,pending=null,revoked=false;
 const tracking={request_id:'del-test',receipt:'a'.repeat(43),expires_at:Date.now()/1000+3600};
 const c={document:{getElementById:get,createElement:()=>({})},localStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},JustHereAuth:{getUid:()=>memory.get('jh_uid')||'',getToken:()=>memory.get('jh_guest_token')||''},Date,Number,Error,JSON,encodeURIComponent,fetch:async(url,options)=>{
  calls.push({url,options});if(pending)return pending;
  if(url.startsWith('/v1/me/deletion?')&&revoked)return {ok:false,status:401};
  const data=url==='/v1/me/deletion/receipt'?{tracking}:{request:row,...(options.method==='POST'&&url==='/v1/me/deletion'?{tracking}:{})};
  return {ok:true,json:async()=>data};
 }};
 vm.runInNewContext(source,c);
 return {get,memory,calls,tracking,set row(v){row=v},set pending(v){pending=v},set revoked(v){revoked=v}};
}
(async()=>{
 const f=fixture();await tick();assert(f.get('deletion-progress').hidden);assert.equal(f.get('submit').disabled,false);
 await f.get('deletion-form').onsubmit({preventDefault(){}});assert.equal(f.calls.length,1);assert(f.get('status').textContent.includes('동의'));
 f.row={id:'del-test',status:'requested',updated_at:'2026-11-07T00:00:00Z',reasons:['지급 처리 중이에요.'],next_action:'담당자 확인 중'};
 f.get('confirm').checked=true;await f.get('deletion-form').onsubmit({preventDefault(){}});assert.equal(f.calls.filter(x=>x.options.method==='POST'&&x.url==='/v1/me/deletion').length,1);assert(f.get('deletion-form').hidden);assert(!f.get('deletion-progress').hidden);assert(f.get('status').textContent.includes('삭제되지는'));assert.equal(f.get('deletion-reasons').children[0].textContent,'지급 처리 중이에요.');assert(f.memory.get('jh_guest_token'));
 f.row={id:'del-test',status:'reviewing'};await f.get('refresh-deletion').onclick();assert(f.get('status').textContent.includes('검토'));
 f.row={id:'del-test',status:'withdrawn'};await f.get('withdraw').onclick();assert.equal(f.get('deletion-form').hidden,false);assert(f.get('withdraw').hidden);assert.equal(f.get('deletion-reasons').children.length,0);
 let resolve;f.pending=new Promise(r=>resolve=r);const loading=f.get('refresh-deletion').onclick();const before=f.calls.length;await f.get('refresh-deletion').onclick();assert.equal(f.calls.length,before);f.memory.set('jh_uid','other');resolve({ok:true,json:async()=>({request:{id:'del-test',status:'requested'}})});await loading;assert(f.get('deletion-progress').hidden);assert(f.get('deletion-form').hidden);assert(f.get('status').textContent.includes('현재 계정'));
 const removed=fixture();await tick();removed.memory.set('jh_deletion_receipt',JSON.stringify({...removed.tracking,uid:'owner'}));removed.row={id:'del-test',status:'active_data_deleted',backup_status:'pending',full_deletion_complete:false};removed.revoked=true;await removed.get('refresh-deletion').onclick();assert.equal(removed.memory.get('jh_guest_token'),undefined);assert.equal(removed.memory.get('jh_uid'),undefined);assert(removed.memory.has('jh_deletion_receipt'));assert(removed.get('status').textContent.includes('백업'));assert(removed.get('status').textContent.includes('전체 삭제 완료 상태는 아니'));assert(removed.get('withdraw').hidden);await removed.get('refresh-deletion').onclick();assert(removed.calls.some(x=>x.url==='/v1/me/deletion/status'&&!x.options.headers['X-Guest-Token']));
 const switched=fixture();await tick();switched.memory.set('jh_deletion_receipt',JSON.stringify({...switched.tracking,uid:'previous-owner'}));switched.revoked=true;await switched.get('refresh-deletion').onclick();assert.equal(switched.memory.get('jh_guest_token'),'private-token');assert(!switched.calls.some(x=>x.url==='/v1/me/deletion/status'));
 const html=fs.readFileSync('web/account-delete.html','utf8');assert(html.includes('account-delete.js'));assert(html.includes('070-8691-1886'));
 for(const file of ['web/account-delete.html','web/admin-account-deletions.html'])for(const match of fs.readFileSync(file,'utf8').matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
 console.log('PASS deletion UI: consent, owner progress/reasons, review/withdraw, duplicate/account switch, scoped tracking after revocation, only confirmed own identity clearing, backup-pending truthfulness, inline syntax');
})().catch(e=>{console.error(e);process.exitCode=1});
