const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web/app.js','utf8');
const body=source.slice(source.indexOf('function renderRecruitmentState()'),source.indexOf('function renderRewardOffer'));
const elements={};const get=id=>elements[id]??={};
const parts={};const promo={querySelector:key=>parts[key]??={}};
const context={state:{meta:{}},$:get,document:{querySelector:()=>promo}};
vm.createContext(context);vm.runInContext(body,context);
function render(meta){context.state.meta=meta;context.renderRecruitmentState();}
render({rewards:{enabled:true}});assert(parts.strong.textContent.includes('오픈 예정'));assert(parts['.promo-ticket'].hidden);
render({rewards:{enabled:true},reward_identity:{required:true,configured:false}});assert.equal(promo.href,'/my#reward-identity');
render({rewards:{enabled:true},reward_identity:{required:true,configured:true}});assert.equal(promo.href,'/my#beta-apply');assert.equal(parts['.promo-ticket'].hidden,false);
render({rewards:{enabled:false},reward_identity:{required:false}});assert.equal(promo.href,'/my#activity');assert(parts['.promo-ticket'].hidden);
assert.equal(get('reward-entry').href,promo.href);
console.log('PASS recruitment banner: unknown and unconfigured fail closed, ready links to terms, paused hides reward ticket, home/done agree');
