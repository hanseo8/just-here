const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('web/app.js','utf8');
const start=src.indexOf('async function swipe('),end=src.indexOf('\nfunction setShareStatus',start);
let requests=0,resolveRequest,shown=0,sequence=0;
const c={state:{swiping:false,modeSwitching:false,gestureSettling:false,intent:'visit',uid:'fixture'},
 currentCard:()=>({card_id:'card-a',menu_id:'menu-a'}),isDesignPreview:()=>false,
 beginReq:()=>++sequence,isCurrentReq:n=>n===sequence,actionIdFor:()=> 'fixture-action',sessionActionBody:x=>x,
 api:async()=>{requests++;return new Promise(resolve=>resolveRequest=resolve)},setSwipeBusy(){},settleAction(){},
 markSwipeHintSeen(){},track(){},showMatchThenHandoff(){shown++},applyFeed:()=>false,renderCard(){},setFeedHint(){},syncUndoBtn(){},console};
vm.createContext(c);vm.runInContext(src.slice(start,end),c);
(async()=>{
 c.state.modeSwitching=true;
 const guarded=c.swipe('lets_go');
 assert.equal(requests,0,'mode switch must block button selection');await guarded;
 c.state.modeSwitching=false;
 const pending=c.swipe('lets_go');assert.equal(requests,1);sequence++;
 resolveRequest({place_name:'old response'});assert.equal(await pending,false);assert.equal(shown,0,'stale reply must not open the chosen screen');
 const fresh=c.swipe('lets_go');resolveRequest({place_name:'current response'});assert.equal(await fresh,true);assert.equal(shown,1);
 assert.equal(c.state.swiping,false);
 const undoStart=src.indexOf('async function undoCard('),undoEnd=src.indexOf('\nfunction openHandoff',undoStart);
 vm.runInContext(src.slice(undoStart,undoEnd),c);
 c.state.canUndo=true;c.state.sessionId='fixture';c.state.modeSwitching=true;
 let before=requests;assert.equal(await c.undoCard(),false);assert.equal(requests,before);
 c.state.modeSwitching=false;c.state.gestureSettling=true;assert.equal(await c.undoCard(),false);assert.equal(requests,before);
 c.state.gestureSettling=false;c.applyFeed=()=>true;
 const undo=c.undoCard();assert.equal(requests,before+1);assert.equal(await c.undoCard(),false);
 resolveRequest({cards:[{menu_id:'previous'}]});assert.equal(await undo,true);assert(!c.state.swiping);
 c.state.canUndo=false;before=requests;assert.equal(await c.undoCard(),false);assert.equal(requests,before);
 const photoStart=src.indexOf('function placePhotoLinks('),photoEnd=src.indexOf('\nfunction renderDetailModal',photoStart);
 vm.runInContext(src.slice(photoStart,photoEnd),c);
 const links=c.placePhotoLinks({place_id:'kakao_12345',place_name:'가게',address:'주소'});
 assert(links.includes('https://place.map.kakao.com/12345'));assert(links.includes('https://map.naver.com/p/search/'));
 assert.equal(c.placePhotoLinks({is_brand:true}),'');
 assert(!c.placePhotoLinks({place_name:'"><script>alert(1)</script>'}).includes('<script>'));
 const hosts={'feed-undo-slot':{appendChild(e){e.parentElement=this}},'adjust-undo-slot':{appendChild(e){e.parentElement=this}}};
 const previous={classList:{toggle(k,v){this[k]=v}}};previous.parentElement=hosts['feed-undo-slot'];
 const nav={$:id=>id==='btn-undo'?previous:hosts[id],state:{canUndo:false}};vm.createContext(nav);
 const syncStart=src.indexOf('function syncUndoBtn('),syncEnd=src.indexOf('\nasync function submitAdjust',syncStart);
 vm.runInContext(src.slice(syncStart,syncEnd),nav);nav.syncUndoBtn();assert(previous.disabled);assert.equal(previous.classList.hidden,false);
 nav.state.canUndo=true;nav.state.adjustNeeded=true;nav.syncUndoBtn();assert.equal(previous.parentElement,hosts['adjust-undo-slot']);
 nav.state.adjustNeeded=false;nav.syncUndoBtn();assert.equal(previous.parentElement,hosts['feed-undo-slot']);assert(!previous.disabled);
 console.log('PASS navigation races: transition and stale guards, centre choice, locked/first-card undo, duplicate undo blocked, exact Kakao ID and encoded Naver links');
})().catch(e=>{console.error(e);process.exitCode=1});
