const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const tick=()=>new Promise(r=>setImmediate(r));
const nodes={},get=id=>nodes[id]??={hidden:false,value:'',textContent:'',setAttribute(){},replaceChildren(...children){this.children=children;this.value=children[0]?.value||''}};
const button={textContent:'',disabled:false},form=get('bank-form');form.querySelector=()=>button;form.reset=()=>{form.resets=(form.resets||0)+1};
const fields=new Map([['bank','Fixture Bank'],['account','123456789012'],['holder','Fixture'],['consent',true]]);
let data={identity:{required:true,verified:true},payout_config:{enabled:true},receipts:[],payouts:[]},calls=[],resolve;
const c={window:{JustHereAuth:{getUid:()=> 'owner'}},document:{getElementById:get,createElement:()=>({})},crypto:{randomUUID:()=>String(Math.random())},Option:function(text,value){return {text,value}},FormData:function(){return {get:k=>fields.get(k),has:k=>fields.has(k)}},jsonApi:async(path,options)=>{calls.push(JSON.parse(options.body));return new Promise(r=>resolve=r)},start:async()=>{c.window.renderRewardPayouts(data);return data}};
vm.runInNewContext(fs.readFileSync('web/payouts.js','utf8'),c);
(async()=>{
 await tick();assert(get('bank-payout').hidden);
 data={...data,receipts:[{id:'a',status:'approved',reward_points:300,place_name:'Restaurant'}]};c.window.renderRewardPayouts(data);assert(!get('bank-payout').hidden);assert(button.textContent.includes('300'));
 const submit=form.onsubmit({preventDefault(){}});await form.onsubmit({preventDefault(){}});assert.equal(calls.length,1);assert(button.disabled);assert(get('bank-message').textContent.includes('아직 송금'));
 data={...data,payouts:[{id:'pay1',receipt_id:'a',status:'pending',amount_krw:300,account_tail:'9012'}]};resolve({});await submit;assert.equal(button.disabled,false);assert(get('bank-payout').hidden);assert(get('bank-history').children[0].textContent.includes('지급 대기'));assert(get('bank-message').textContent.includes('접수'));
 data={...data,payouts:[{...data.payouts[0],status:'rejected',reason:'계좌 확인 필요'}]};c.window.renderRewardPayouts(data);assert(!get('bank-payout').hidden);assert(get('bank-history').children[0].textContent.includes('포인트 반환'));assert(get('bank-history').children[0].textContent.includes('계좌 확인 필요'));
 data={...data,payouts:[{...data.payouts[0],status:'paid'}]};c.window.renderRewardPayouts(data);assert(get('bank-payout').hidden);assert(get('bank-history').children[0].textContent.includes('지급 완료'));
 console.log('PASS payout UI: live refresh, 300 KRW amount, busy duplicate guard, pending not paid, rejected refund/retry and paid exclusion');
})().catch(e=>{console.error(e);process.exitCode=1});
