const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web/analytics-client.js','utf8');
let now=1000000,seq=0;const memory=new Map();
function load(search='',host='justthis.co.kr',blocked=false,native=false){
 const c={window:native?{JustHereNative:{}}:{},location:{search,hostname:host},URLSearchParams,Date:{now:()=>now},crypto:{randomUUID:()=>`visit-fixture-${String(++seq).padStart(8,'0')}`},
 sessionStorage:{getItem:k=>{if(blocked)throw Error('blocked');return memory.get(k)||null},setItem:(k,v)=>{if(blocked)throw Error('blocked');memory.set(k,v)}}};
 vm.createContext(c);vm.runInContext(source,c);return c.window.JustHereAnalytics;
}
let client=load('?utm_source=threads&utm_campaign=launch&utm_content=hook&token=private&lat=37.1');
const first=client.context();assert.equal(first.utm_source,'threads');assert.equal(client.context().visit_id,first.visit_id);
assert(!JSON.stringify(first).includes('private'));assert(!JSON.stringify(first).includes('37.1'));
assert.equal(load('').context().utm_content,'hook');
assert.notEqual(load('?utm_source=threads&utm_content=other').context().visit_id,first.visit_id);
now+=31*60*1000;assert.equal(load('').context().utm_source,undefined);
client=load('?utm_source=https://private.example&email=private@example.com');assert.equal(client.context().utm_source,undefined);
for(const [search,host] of [['?design=food','justthis.co.kr'],['?analytics_test=1','justthis.co.kr'],['','127.0.0.1']])assert.equal(load(search,host).context().traffic_type,'test');
client=load('?utm_source=threads','justthis.co.kr',true);const blocked=client.context();assert.equal(client.context().visit_id,blocked.visit_id);
assert(load('','localhost',false,true).context().visit_id); // native WebView localhost is a real install
// A browser that refuses sendBeacon must still try fetch; accepted beacons are not sent twice.
const app=fs.readFileSync('web/app.js','utf8');const trackSource=app.slice(app.indexOf('function track('),app.indexOf('function useFallbackLocation('));
let sent=0,beacons=0,accepted=false;
const c={isDesignPreview:()=>false,state:{sessionId:'new-session',mealContext:'meal'},window:{JustHereAnalytics:{context:()=>first}},navigator:{sendBeacon:()=>{beacons++;return accepted}},Blob,fetch:()=>{sent++;return Promise.resolve()}};
vm.createContext(c);vm.runInContext(trackSource,c);c.track('app_open');assert.equal(sent,1);accepted=true;c.track('app_open');assert.equal(sent,1);assert.equal(beacons,2);
c.window.JustHereAnalytics.context=()=>({traffic_type:'test'});c.track('app_open');assert.equal(beacons,2);
c.window.JustHereAnalytics.context=()=>first;c.window.JustHereNative={};c.track('app_open');assert.equal(beacons,2);assert.equal(sent,2);
const html=fs.readFileSync('web/analytics.html','utf8');assert(html.includes('p.first_pack_choose_rate'));assert(!html.includes('`${p.first_pack_no_choice_rate'));
// Entry must be observable before metadata/auth networking, and session_start must use its new response ID.
const init=app.slice(app.indexOf('async function init()'),app.indexOf('// 카카오 authorize 콜백'));
assert(init.indexOf('track("app_open"')<init.indexOf('await api("/v1/meta")'));
let captured;
const session={state:{sessionId:'old-session',tasteChoices:[]},ensureFreshLocation:async()=>{},beginReq:()=>1,api:async()=>({session_id:'new-session'}),track:(name,props)=>captured=props,applyFeed:()=>false};
vm.createContext(session);vm.runInContext(app.slice(app.indexOf('async function startSession()'),app.indexOf('async function refreshFeed()')),session);
session.startSession().then(()=>{assert.equal(captured.session_id,'new-session');console.log('PASS acquisition client: campaign persistence/expiry, safe labels, native/WebView distinction, beacon fallback, early entry, new session binding and correct choose label');}).catch(e=>{console.error(e);process.exitCode=1});
