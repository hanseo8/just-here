const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={};const get=id=>elements[id]??={focus(){this.focused=true}};
let requests=0,refreshes=0,opened='';
const c={window:{JustHereAuth:{getUid:()=> 'test-owner'},JustHereMy:{open:id=>opened=id}},document:{getElementById:get},AbortController,setTimeout,clearTimeout,
jsonApi:async()=>{requests++;return {ok:true}},start:async()=>{refreshes++}};
vm.createContext(c);vm.runInContext(fs.readFileSync('web/beta-progress.js','utf8'),c);
(async()=>{
 const base={reward_config:{enabled:true},identity:{required:true,configured:false,verified:false}};
 c.window.renderBetaProgress({enrolled:false},base);await get('beta-apply-button').onclick();assert.equal(requests,0);assert.equal(opened,'reward-identity');
 c.window.renderBetaProgress({enrolled:false},{...base,identity:{required:true,configured:true,verified:false}});await get('beta-apply-button').onclick();assert.equal(requests,0);assert.equal(get('beta-connect-action').hidden,false);
 c.window.renderBetaProgress({enrolled:false},{...base,identity:{required:true,configured:true,verified:true}});await get('beta-apply-button').onclick();assert.equal(requests,1);assert.equal(refreshes,1);assert.equal(get('beta-apply-button').disabled,false);
 c.window.renderBetaProgress({enrolled:false},{...base,beta_application:{applied:true}});await get('beta-apply-button').onclick();assert.equal(requests,1);
 console.log('PASS beta application UI: unconfigured/unverified blocked, one verified request, refresh next action after success, already-applied does not resubmit');
})().catch(e=>{console.error(e);process.exitCode=1});
