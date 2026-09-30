const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync('web/app.js', 'utf8');
const start = source.indexOf('let cardPhotoGeneration = 0;');
const end = source.indexOf('\nfunction distanceLabel', start);
const nodes = {};
function node(id) {
  return nodes[id] ||= { textContent: '', style: {}, classList: {
    values: new Set(), add(x) { this.values.add(x); }, remove(x) { this.values.delete(x); },
    contains(x) { return this.values.has(x); }
  }, removeAttribute(name) { delete this[name]; } };
}
let current, requests = [], prefetched = 0;
const context = { AbortController, $: node, currentCard: () => current,
  usablePhoto: c => c?.image_url ? {url:c.image_url, role:'store'} : null,
  visitExamplePhoto: c => c?.fallback ? {atlasIndex:0, role:'example', example:true} : null,
  renderVisitExample: (wrap,img,card,photo) => {
    if (photo?.atlasIndex == null) return false;
    img.classList.add('hidden'); img.removeAttribute('src'); wrap.classList.remove('hidden');
    node('card').classList.add('has-photo'); return true;
  },
  cardPresentation: c => ({title:c.card_id}), showExampleCaption: () => {},
  detailChipLabel: () => '주소·가게 정보', EXAMPLE_PHOTO_CAP:'예시',
  state: {cards:[{}, {image_url:'/paid-next', photo_source:'google_places'}]},
  Image: function() { prefetched++; },
  fetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve}))
};
vm.createContext(context);
vm.runInContext(source.slice(start,end), context);
(async () => {
  current = {card_id:'a', image_url:'/a', photo_source:'google_places', photo_meta_url:'/meta-a'};
  context.setCardPhoto(current);
  const oldError = node('card-photo-img').onerror;
  const oldLoad = node('card-photo-img').onload;
  current = {card_id:'b', image_url:'/b', photo_source:'google_places', photo_meta_url:'/meta-b', fallback:true};
  context.setCardPhoto(current);
  assert.equal(requests[0].options.signal.aborted,true);
  oldError(); oldLoad();
  assert.equal(node('card-photo-img').src,'/b');
  assert.equal(node('card').classList.contains('has-photo'),false);
  node('card-photo-img').onerror();
  assert.equal(node('card').classList.contains('has-photo'),true);
  assert.equal(node('screen-feed').classList.contains('is-nophoto'),false);
  assert.equal(node('card-media').classList.contains('hidden'),false);
  assert.equal(node('card-photo-source').textContent,'');
  requests[1].resolve({ok:true,json:async()=>({attributions:[{name:'late'}]})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(node('card-photo-source').textContent,'');
  current = {card_id:'c', image_url:'/c', photo_source:'google_places'};
  context.setCardPhoto(current);
  node('card-photo-img').onerror();
  assert.equal(node('screen-feed').classList.contains('is-nophoto'),true);
  assert.equal(node('card-media').classList.contains('hidden'),true);
  assert.equal(prefetched,0);
  console.log('photo state: pass (stale callbacks, example fallback, failed layout, late attribution, paid prefetch)');
})().catch(e=>{ console.error(e); process.exitCode=1; });
