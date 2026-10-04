const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('web/rewards.html', 'utf8');
const code = source.match(/    let guestRefresh = null;\r?\n    async function jsonApi[^\n]+/)[0];
(async () => {
  let refreshed = 0;
  const requests = [];
  const context = {
    URL, location: {origin:'https://example.test'}, currentUid:'old',
    window: {JustHereAuth: {getToken:()=>'public-test-token', ensureGuest:async()=>{refreshed++;return {uid:'own-new-uid'};}}},
    fetch:async(path)=>{requests.push(path);return {status:401,ok:false,json:async()=>({detail:'guest token required'})};}
  };
  vm.createContext(context); vm.runInContext(code, context);
  await assert.rejects(context.jsonApi('/v1/rewards/me?uid=old'));
  assert.equal(refreshed,1);
  assert.equal(requests.length,2);
  assert.equal(requests[1],'/v1/rewards/me?uid=own-new-uid');
  await assert.rejects(context.jsonApi('/v1/rewards/payouts',{method:'POST'}));
  assert.equal(refreshed,1); // Mutations are never automatically retried.
  assert.equal(requests.length,3);
  context.fetch=async()=>({status:503,ok:false,json:async()=>({detail:{reason:'disabled'}})});
  await assert.rejects(context.jsonApi('/v1/rewards/me?uid=old'),/disabled/);
  assert.equal(refreshed,1);
  console.log('PASS: one bounded auth refresh, own UID retry, no mutation replay, disabled status preserved');
})().catch(error=>{console.error(error);process.exitCode=1;});
