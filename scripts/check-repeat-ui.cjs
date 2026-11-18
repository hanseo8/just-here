const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web/app.js','utf8');
function fn(name){const at=source.search(new RegExp('^(?:async )?function '+name+'\\(','m'));assert(at>=0);const rest=source.slice(at),next=rest.slice(1).search(/\n(?:async )?function /);return rest.slice(0,next+1);}
function element(tag='div'){return {tagName:tag,children:[],textContent:'',classList:{add(){},remove(){},toggle(){}},append(...x){this.children.push(...x)},replaceChildren(){this.children=[]}};}
const nodes={};const get=id=>nodes[id]??=element();let opened=0,fulfilled=[],events=[];
const c={state:{locationReady:true,lat:37.5,lng:127,starting:false,savedTaste:['bibimbap','unknown','bibimbap','pasta','gukbap','pizza']},
 $:get,TASTE_CATEGORIES:['bibimbap','pasta','gukbap','pizza'].map(key=>({key})),TASTE_CAT_MAX:3,track:(...args)=>events.push(args),
 openTasteFlow(){opened++;c.state.tasteChoices=[]},openFulfillment(){fulfilled.push([...c.state.tasteChoices])},syncStartState(){},console};
vm.createContext(c);vm.runInContext(fn('reusableTaste')+fn('onStartClick'),c);
(async()=>{
 await c.onStartClick({reuseTaste:true});assert.deepEqual(fulfilled[0],['bibimbap','pasta','gukbap']);
 await c.onStartClick({type:'click'});assert.equal(fulfilled.length,1);assert.equal(opened,2);
 c.state.savedTaste=['retired-key'];await c.onStartClick({reuseTaste:true});assert.equal(fulfilled.length,1);
 assert.equal(events.length,1);assert.equal(events[0][0],'taste_done');assert.equal(events[0][1].source,'saved_taste');
 const m={window:{addEventListener(){}},document:{getElementById:get,createElement:element},location:{hash:''}};
 vm.createContext(m);vm.runInContext(fs.readFileSync('web/my-ui.js','utf8'),m);
 m.window.JustHereMy.renderRecentChoices([{place_name:'<img src=x onerror=bad()>',selected_at:'2026-11-18T01:00:00Z',map_url:'javascript:bad'},
 {place_name:'검증 가게',selected_at:'2026-11-18T01:00:00Z',map_url:'https://map.kakao.com/link/map/123'}]);
 const rows=get('recent-choice-list').children;
 assert.equal(rows[0].children[0].children[0].textContent,'<img src=x onerror=bad()>');assert.equal(rows[0].children.length,1);
 assert.equal(rows[1].children[1].href,'https://map.kakao.com/link/map/123');assert(rows[1].children[1].rel.includes('noopener'));
 m.window.JustHereMy.renderRecentChoices([]);assert(get('recent-choice-list').children[0].textContent.includes('아직'));
 console.log('PASS repeat UI: explicit saved-taste reuse, valid unique 3-item cap, normal choose remains fresh, invalid old tastes, safe recent text/map links and empty state');
})().catch(e=>{console.error(e);process.exitCode=1});
