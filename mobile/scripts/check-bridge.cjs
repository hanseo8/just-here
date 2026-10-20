const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../src/native.js'),'utf8').replace(/^import .*;$/gm,'');
(async()=>{
 for(const origin of ['https://localhost','capacitor://localhost']){
  const calls=[],events={};
  const context={URL,Headers,Request,Promise,location:{href:origin+'/index.html',origin:new URL(origin).origin,pathname:'/index.html'},
    navigator:{},Capacitor:{isNativePlatform:()=>true},Geolocation:{},Browser:{},App:{addListener:()=>{}},
    document:{addEventListener:(name,fn)=>events[name]=fn},history:{length:1},
    window:{fetch:async(...args)=>{calls.push(args);return new Response('{}')},alert:()=>{}}};
  vm.createContext(context);vm.runInContext(source,context);
  await context.window.fetch('/v1/rewards/me?uid=test',{headers:{'X-Guest-Token':'test'}});
  assert.equal(calls[0][0],'https://justthis.co.kr/v1/rewards/me?uid=test');
  await context.window.fetch('/static/tastes/gukbap.jpg');assert.equal(calls[1][0],'/static/tastes/gukbap.jpg');
  await assert.rejects(context.window.fetch('https://untrusted.example/data',{headers:{'X-Guest-Token':'test'}}),/Credential destination/);
  assert.equal(calls.length,2);
  assert.equal(context.window.JustHereNative.remoteUrl('/v1/photo?token=public'),'https://justthis.co.kr/v1/photo?token=public');
 }
 console.log('PASS: Android/iOS local-origin API mapping, static assets, photo URL, credential destination isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
