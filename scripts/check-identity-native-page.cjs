const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const script=fs.readFileSync('web/identity-native.js','utf8'), id='jh-identity-'+'x'.repeat(32),state='a'.repeat(64);
function page({search='',hash=''}={}){
 const els={},requests=[];const get=k=>els[k]??={hidden:true};
 const c={document:{getElementById:get},location:{search,hash,pathname:'/static/identity-native.html'},history:{replaceState(){}},URLSearchParams,Date,Number,JSON,Promise,Error,encodeURIComponent,decodeURIComponent,setTimeout,clearTimeout,window:{PortOne:{requestIdentityVerification:async args=>{requests.push(args);return {identityVerificationId:id}}}}};
 vm.runInNewContext(script,c);return {els,requests};
}
(async()=>{
 const initial=page();assert(initial.els.begin.hidden);assert(initial.els.state.textContent.includes('만료'));
 const cfg={id,state,expires:Date.now()+60000,storeId:'store',channelKey:'channel'},f=page({hash:'#'+encodeURIComponent(JSON.stringify(cfg))});assert.equal(f.els.begin.hidden,false);assert.equal(f.requests.length,0);await f.els.begin.onclick();assert.equal(f.requests[0].forceRedirect,true);assert.equal(new URL(f.requests[0].redirectUrl).origin,'https://justthis.co.kr');assert.equal(new URL(f.requests[0].redirectUrl).searchParams.get('state'),state);
 const returned=page({search:'?identityVerificationId='+id+'&state='+state});assert.equal(returned.els.return.hidden,false);assert(returned.els.return.href.startsWith('justthis://identity-complete?'));assert.equal(returned.requests.length,0);
 const failed=page({search:'?identityVerificationId='+id+'&state='+state+'&code=FAILURE'});assert(failed.els.state.textContent.includes('취소'));assert.equal(failed.requests.length,0);
 const bad=page({search:'?identityVerificationId='+id+'&state=invalid'});assert(bad.els.return.hidden);
 const duplicate=page({search:'?identityVerificationId='+id+'&state='+state+'&state='+state});assert(duplicate.els.return.hidden);
 const expired=page({hash:'#'+encodeURIComponent(JSON.stringify({...cfg,expires:1}))});assert(expired.els.begin.hidden);
 assert(!script.includes('guest_token'));assert(!script.includes('localStorage'));assert(!script.includes('/identity/complete'));
 console.log('PASS provider handoff page: consented launch, forced redirect, fixed return destination, cancel/malformed/duplicate/expiry, no credentials or identity grant');
})().catch(e=>{console.error(e);process.exitCode=1});
