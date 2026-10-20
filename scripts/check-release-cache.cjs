const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={}, writes=[];
let response=new Response('ok');
const context={URL,Response,self:{location:{origin:'https://example.test'},addEventListener:(k,v)=>listeners[k]=v},
  caches:{open:async()=>({put:async(r)=>writes.push(r.url)}),match:async()=>undefined},fetch:async()=>response};
vm.createContext(context);vm.runInContext(fs.readFileSync('web/sw.js','utf8'),context);
async function request(path,headers={}){let promise;listeners.fetch({request:new Request('https://example.test'+path,{headers}),respondWith:p=>promise=p});if(promise)await promise;await Promise.resolve();return !!promise;}
(async()=>{
 for(const path of ['/my','/rewards','/admin/rewards','/static/admin-coupons.html','/static/merchant-coupons.html','/v1/rewards/me','/?design=done','/?v=test'])assert.equal(await request(path),false,path);
 assert.equal(await request('/static/styles.css',{'X-Guest-Token':'test'}),false);
 assert.equal(await request('/static/styles.css'),true);assert.equal(writes.length,1);
 response=new Response('private',{headers:{'Cache-Control':'no-store'}});await request('/static/test.json');assert.equal(writes.length,1);
 response=new Response('failure',{status:500});await request('/static/test.json');assert.equal(writes.length,1);
 const index=fs.readFileSync('web/index.html','utf8'),sw=fs.readFileSync('web/sw.js','utf8');
 for(const asset of index.matchAll(/(?:href|src)="(\/static\/(?:app\.js|styles\.css)[^"]+)"/g))assert.ok(sw.includes(asset[1]),'cache asset matches current HTML');
 console.log('PASS: private pages/API/previews bypass cache; credentials/no-store/errors not cached; shell versions aligned');
})().catch(e=>{console.error(e);process.exitCode=1});
