const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={};const get=id=>elements[id]??={checked:false,focus(){this.focused=true}};
const memory=new Map();let calls=[],providerCalls=0;
const c={window:{JustHereAuth:{getUid:()=> 'guest-a',setIdentity(uid,type,token){c.saved={uid,type,token}}}},
 document:{getElementById:get},localStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
 location:{origin:'https://justthis.co.kr',pathname:'/my',search:''},history:{replaceState(){}},
 URLSearchParams,Date,Promise,Error,setTimeout,clearTimeout,currentUid:'guest-a',start:async()=>{c.refreshed=true},
 jsonApi:async(path,opts)=>{calls.push(path);if(path.endsWith('/start'))return {identityVerificationId:'attempt-owned',storeId:'store',channelKey:'channel',expires_at:Math.floor(Date.now()/1000)+600};return {uid:'existing-owner',guest_token:'test-token'}}};
c.window.PortOne={requestIdentityVerification:async args=>{providerCalls++;assert.equal(args.identityVerificationId,'attempt-owned');return {identityVerificationId:'attempt-owned'}}};
vm.createContext(c);vm.runInContext(fs.readFileSync('web/reward-identity.js','utf8'),c);
(async()=>{
 c.window.renderRewardIdentity({identity:{required:true,configured:false,verified:false}});await get('verify-reward-identity').onclick();assert.equal(calls.length,0);assert(get('identity-message').textContent.includes('준비'));
 c.window.renderRewardIdentity({identity:{required:true,configured:true,verified:false}});await get('verify-reward-identity').onclick();assert.equal(calls.length,0);assert(get('identity-message').textContent.includes('동의'));
 get('identity-consent').checked=true;await get('verify-reward-identity').onclick();assert.equal(providerCalls,1);assert.deepEqual(calls,['/v1/rewards/identity/start','/v1/rewards/identity/complete']);assert.equal(c.saved.uid,'existing-owner');assert.equal(c.saved.type,'phone');assert(c.refreshed);assert.equal(memory.size,0);
 c.window.JustHereNative={};calls=[];c.window.renderRewardIdentity({identity:{required:true,configured:true,verified:false}});await get('verify-reward-identity').onclick();assert.equal(calls.length,0);assert(get('identity-message').textContent.includes('검수'));
 const html=fs.readFileSync('web/rewards.html','utf8');for(const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
 console.log('PASS phone identity UI: not configured, consent, server start/complete, recovery, native fail-closed, inline syntax');
})().catch(e=>{console.error(e);process.exitCode=1});
