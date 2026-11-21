const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes={};function get(id){return nodes[id]??={textContent:'',attrs:{},files:[],events:{},clicks:0,setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},click(){this.clicks++},addEventListener(k,v){this.events[k]=v}}}
const context={document:{getElementById:get}};vm.createContext(context);vm.runInContext(fs.readFileSync('web/receipt-picker.js','utf8'),context);
const input=get('receipt-image');get('receipt-camera').onclick();assert.equal(input.attrs.capture,'environment');assert.equal(input.clicks,1);
input.files=[{name:'receipt.jpg'}];input.events.cancel();assert(get('image-status').textContent.includes('유지'));
get('receipt-album').onclick();assert.equal(input.attrs.capture,undefined);assert.equal(input.clicks,2);assert.equal(input.files[0].name,'receipt.jpg');
input.files=[];input.events.cancel();assert(get('image-status').textContent.includes('취소'));
const html=fs.readFileSync('web/admin-rewards.html','utf8');for(const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))if(m[1].trim())new vm.Script(m[1]);
console.log('PASS camera/album preserve one upload field, capture selection, cancel retains prior file, no submission; admin inline syntax');
