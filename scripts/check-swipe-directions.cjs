const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8'),events={},globalEvents={},actions=[],animations=[];let reduced=false,finishAnimation=null,delayAnimation=false,identity='a';
const card={style:{},classList:{add(){},remove(){}},getBoundingClientRect:()=>({width:360}),animate(frames,options){animations.push({frames,options});return {finished:delayAnimation?new Promise(r=>finishAnimation=r):Promise.resolve(),cancel(){}}},addEventListener:(n,f)=>events[n]=f},detail={classList:{contains:()=>true}};
const context={$:id=>id==='card'?card:detail,state:{canUndo:true},window:{innerWidth:390,addEventListener:(n,f)=>globalEvents[n]=f},currentCard:()=>({card_id:identity}),prefersReducedMotion:()=>reduced,setSwipeBusy(){},setSwipeDir(){},markSwipeHintSeen(){},setFeedHint(){},syncUndoBtn(){},undoCard:async()=>{actions.push("undo");return true},swipe:async a=>{actions.push(a);return true}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('function setupSwipeGestures()'),source.indexOf('function setupCardKeys()')),context);context.setupSwipeGestures();
const target={closest:()=>null};async function drag(x,y=0,t=target){events.mousedown({clientX:200,clientY:200,target:t});globalEvents.mousemove({clientX:200+x,clientY:200+y});await globalEvents.mouseup()}
(async()=>{
  await drag(-150);await drag(150);assert.deepEqual(actions,['undo','nope']);assert(animations[0].frames[1].transform.includes('-490px'));assert.equal(card.style.transform,'');assert.equal(context.state.gestureSettling,false);
  await drag(20);await drag(10,150);await drag(150,0,{closest:()=>({})});context.state.swiping=true;await drag(-150);assert.equal(actions.length,2);context.state.swiping=false;
  events.touchstart({touches:[{clientX:200,clientY:200}],target});events.touchmove({touches:[{clientX:40,clientY:200}]});assert(card.style.transform.includes('rotate('));events.touchcancel();await events.touchend();assert.equal(actions.length,2);assert.equal(card.style.transform,'');
  const before=animations.length;reduced=true;await drag(-150);assert.equal(animations.length,before);assert.equal(actions.length,3);reduced=false;
  context.undoCard=async()=>false;await drag(-150);assert.equal(card.style.transform,'');assert.equal(context.state.gestureSettling,false);
  context.undoCard=async()=>{actions.push("undo");return true};delayAnimation=true;const pending=drag(-150);assert.equal(context.state.gestureSettling,true);await drag(150);assert.equal(actions.length,3);identity='b';finishAnimation();await pending;assert.equal(actions.length,3);assert.equal(context.state.gestureSettling,false);
  const html=fs.readFileSync('web/index.html','utf8');assert(!html.includes('class="swipe-cues"'));const footer=html.slice(html.indexOf('<footer class="bottom actions"'),html.indexOf('</footer>',html.indexOf('<footer class="bottom actions"')));assert(footer.indexOf('id="btn-undo"')<footer.indexOf('id="btn-go"'));assert(footer.indexOf('id="btn-go"')<footer.indexOf('id="btn-nope"'));assert(footer.includes('그냥여기'));context.state.canUndo=false;delayAnimation=false;await drag(-150);assert.equal(actions.length,3);
  const buttons={'btn-nope':{textContent:'다른 가게',dataset:{}},'btn-go':{textContent:'여기로 할게',dataset:{}},'btn-undo':{textContent:'이전 가게',dataset:{}}};
  const busyContext={$:id=>buttons[id],state:{canUndo:false},setFeedHint(){}};vm.createContext(busyContext);
  const busyStart=source.indexOf('function setSwipeBusy('),busyEnd=source.indexOf('\nfunction ',busyStart+1);
  vm.runInContext(source.slice(busyStart,busyEnd),busyContext);
  busyContext.setSwipeBusy(true,'nope');busyContext.setSwipeBusy(true,'nope');busyContext.setSwipeBusy(false);
  assert.equal(buttons['btn-nope'].textContent,'다른 가게');assert.equal(buttons['btn-go'].disabled,false);
  console.log('PASS swipe: tilt/fly/next entry, left previous/right next, centre-only selection, first-card previous blocked, vertical/short/control/cancel/busy guards, reduced motion, failed request reset, settling lock and stale-card protection');
})().catch(e=>{console.error(e);process.exitCode=1});
