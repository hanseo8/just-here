const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web/app.js','utf8');
function fn(name){const at=source.search(new RegExp('^(?:async )?function '+name+'\\(','m'));assert(at>=0,name);const rest=source.slice(at);const next=rest.slice(1).search(/\n(?:async )?function /);return next<0?rest:rest.slice(0,next+1);}
function element(){return {textContent:'',disabled:false,value:'',children:[],attrs:{},classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},replaceChildren(){this.children=[]},append(...x){this.children.push(...x)},focus(){this.focused=true}};}
const els={};const get=id=>els[id]??=element();let gps, timers=[], tracked=[], opened=0, request=null;
const c={state:{locationEpoch:0,locationSearchSeq:0,locationReady:false,lat:null,lng:null,watchId:null,starting:false},$:get,
 AbortController,URLSearchParams,
 document:{createElement:element},navigator:{geolocation:{getCurrentPosition(ok,bad){gps={ok,bad}},clearWatch(){},watchPosition(){return 7}}},
 GEO_OPTS:{timeout:8000,enableHighAccuracy:false},GEO_OPTS_FORCE:{timeout:15000,enableHighAccuracy:true,maximumAge:0},setTimeout(fn){timers.push(fn);return timers.length},clearTimeout(){},
 console:{warn(){},error(){}},isInAppBrowser:()=>false,track:(...args)=>tracked.push(args),closeTasteFlow(){},show(){},syncStartState(){},
 setLocStatus(t){get('loc-status').textContent=t},applySmartIntent:async()=>{},beginReq(){},openTasteFlow(){opened++},
 api:async(path,opts)=>{request={path,opts};return {results:[{name:'<img src=x>',address:'서울',lat:37.498,lng:127.028}]}}};
vm.createContext(c);
for(const name of ['useFallbackLocation','openManualLocation','locationSearchStatus','selectManualLocation','searchManualLocation','applyPosition','requestLocation','startWatchingLocation','onStartClick','ensureFreshLocation','performLocationAndWeather','locateAndSyncWeather'])vm.runInContext(fn(name),c);
(async()=>{
 c.useFallbackLocation('권한이 없어요');assert.equal(c.state.lat,null);assert(!c.state.locationReady);assert(get('btn-location-manual').attrs['aria-expanded']==='true');
 const denied=c.requestLocation();gps.bad({code:1});await denied;assert(!c.state.locationReady);assert.equal(c.state.lng,null);
 const failedGPS=gps;await c.onStartClick();assert.strictEqual(gps,failedGPS);assert.equal(opened,0);assert(!c.state.starting);assert(get('location-query').focused);
 const pending=c.requestLocation();const late=gps.ok;
 await c.selectManualLocation({name:'강남역',lat:37.498,lng:127.028});
 late({coords:{latitude:37.3925,longitude:126.645}});await pending;
 assert.equal(c.state.lat,37.498);assert.equal(c.state.lng,127.028);assert.equal(c.state.locationSource,'manual');
 assert.equal(c.state.watchId,null);assert.equal(c.state.sessionId,null);assert(tracked.some(x=>x[0]==='locate_manual'&&x.length===1));
 c.startWatchingLocation();assert.equal(c.state.watchId,null);
 await c.onStartClick();assert.equal(opened,1); // Manual selection proceeds without GPS prompt.
 c.applyFeed=()=>false;vm.runInContext(fn('startSession'),c);await c.startSession();
 assert.equal(request.path,'/v1/session');assert.equal(JSON.parse(request.opts.body).lat,37.498);assert.equal(JSON.parse(request.opts.body).lng,127.028);
 get('location-query').value='강南';await c.searchManualLocation({preventDefault(){}});
 assert.equal(request.path,'/v1/location/search');assert.equal(request.opts.retries,0);assert.equal(JSON.parse(request.opts.body).query,'강南');
 assert.equal(get('location-results').children[0].children[0].children[0].textContent,'<img src=x>');
 assert(!get('btn-location-search').disabled);
 c.api=async()=>({results:[]});await c.searchManualLocation();assert(get('location-search-status').textContent.includes('검색 결과가 없어요'));
 c.api=async()=>{throw Error('fixture')};await c.searchManualLocation();assert(get('location-search-status').textContent.includes('다시 검색'));assert(!get('btn-location-search').disabled);
 let staleReply;c.api=()=>new Promise(resolve=>staleReply=resolve);const searching=c.searchManualLocation();c.state.locationSearchSeq++;
 staleReply({results:[{name:'지난 결과',lat:37.5,lng:127}]});await searching;assert.equal(get('location-results').children.length,0);
 c.state.locationReady=false;c.state.lat=null;c.state.lng=null;c.state.locationSource='';
 const timed=c.requestLocation();const tooLate=gps.ok;timers.at(-1)();timers.at(-1)();await timed;
 tooLate({coords:{latitude:37.5,longitude:127}});assert.equal(c.state.lat,null);
 const fresh=c.ensureFreshLocation();gps.bad({code:1});await assert.rejects(fresh,/위치/);
 c.state.locationFailed=false;let gpsCalls=0;
 c.navigator.geolocation.getCurrentPosition=(ok,bad)=>{gpsCalls++;gps={ok,bad}};
 const automatic=c.locateAndSyncWeather(false);assert.strictEqual(automatic,c.locateAndSyncWeather(true));
 const queuedStart=c.onStartClick();assert.equal(gpsCalls,1);assert(c.state.locationPending);
 gps.ok({coords:{latitude:37.5,longitude:127,accuracy:20}});await automatic;await queuedStart;
 assert.equal(opened,2);assert.equal(gpsCalls,1);assert.equal(c.state.locationTask,null);assert(!c.state.locationPending);assert.equal(c.state.locationSource,'gps');
 let weatherReply;c.api=()=>new Promise(resolve=>weatherReply=resolve);c.setToggleUI=()=>{};c.setMealUI=()=>{};
 vm.runInContext(fn('applySmartIntent'),c);c.state.locationReady=true;c.state.lat=37.498;c.state.lng=127.028;
 const weather=c.applySmartIntent();c.state.locationEpoch++;get('weather-status').textContent='새 지역';
 weatherReply({weather:'rain'});await weather;assert.equal(get('weather-status').textContent,'새 지역');
 const laterWeather=c.applySmartIntent();c.state.intentChoice=(c.state.intentChoice||0)+1;c.state.intent='delivery';
 weatherReply({weather:'clear',suggested_intent:'visit'});await laterWeather;assert.equal(c.state.intent,'delivery');
 assert(!source.includes('FALLBACK_LAT')&&!source.includes('송도 기준'));
 const html=fs.readFileSync('web/index.html','utf8');assert(html.includes('id="location-manual-entry" class="location-manual"'));assert(html.includes('id="location-search-panel" class="hidden"'));
 const init=source.slice(source.indexOf('async function init()'),source.indexOf('// 카카오 authorize 콜백'));
 assert(init.indexOf('void locateAndSyncWeather(false)')<init.indexOf('await api("/v1/meta")'));
 vm.runInContext(fn('syncStartState'),c);
 c.state.locationReady=false;c.state.locationPending=true;c.state.locationFailed=false;c.syncStartState();assert.equal(get('btn-start').textContent,'근처 메뉴 고르기');assert(get('start-hint').textContent.includes('확인하고 있어요'));
 c.state.locationPending=false;c.state.locationFailed=true;c.syncStartState();assert.equal(get('btn-start').textContent,'지역 선택하고 계속');
 c.state.locationReady=true;c.syncStartState();assert.equal(get('btn-start').textContent,'근처 메뉴 고르기');
 // Low precision escalates once; stale first-attempt callbacks cannot overwrite the precise fix.
 c.state.locationReady=false;c.state.lat=null;c.state.lng=null;c.state.sessionId=null;
 const attempts=[];c.navigator.geolocation.getCurrentPosition=(ok,bad,options)=>{attempts.push({ok,bad,options})};
 const precise=c.requestLocation();attempts[0].ok({coords:{latitude:37,longitude:127,accuracy:2400}});
 assert.equal(attempts.length,2);assert(attempts[1].options.enableHighAccuracy);assert.equal(attempts[1].options.maximumAge,0);
 attempts[0].bad({code:1});attempts[1].ok({coords:{latitude:37.5,longitude:127,accuracy:18}});await precise;
 assert.equal(c.state.lat,37.5);assert.equal(c.state.locationAccuracy,18);assert(get('loc-status').textContent.includes('18m'));
 const retained=c.requestLocation(true);attempts.at(-1).bad({code:1});await retained;
 assert.equal(c.state.lat,37.5);assert(get('loc-status').textContent.includes('유지'));assert(get('location-help').textContent.includes('사이트 설정'));
 // Weather can remain pending without locking the locate button.
 c.applySmartIntent=()=>new Promise(()=>{});
 const weatherPending=c.locateAndSyncWeather(true);attempts.at(-1).ok({coords:{latitude:37.5,longitude:127,accuracy:20}});await weatherPending;
 await Promise.resolve();assert(!c.state.locationPending);assert(!get('btn-locate').disabled);
 let watch;c.state.watchId=null;c.navigator.geolocation.watchPosition=ok=>{watch=ok;return 8};c.startWatchingLocation();
 watch({coords:{latitude:36,longitude:128,accuracy:4000}});assert.equal(c.state.lat,37.5);
 c.applySmartIntent=async()=>{};
 const cancelled=c.requestLocation(true);await c.selectManualLocation({name:'강남역',lat:37.498,lng:127.028});
 await cancelled;assert.equal(c.state.cancelLocation,null);
 c.TASTE_CATEGORIES=[];c.syncFulfillment=()=>{};c.state.tasteChoices=[];c.state.intent='delivery';c.state.intentReason='늦은 시간이라 배달 추천';
 vm.runInContext(fn('openFulfillment'),c);c.openFulfillment();assert.equal(c.state.intentReason,'');assert.equal(c.state.intent,'visit');
 console.log('PASS location UI: automatic entry and shared CTA request, fallback only after failure, denied/timeout guards, stale GPS/weather ignored, manual coordinates retained, safe results, no sensitive analytics and clear CTA states');
})().catch(e=>{console.error(e);process.exitCode=1});
