const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('web/analytics.html', 'utf8');
const source = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const elements = {};
const context = vm.createContext({
  document: {
    getElementById(id) { return elements[id] ||= {value:''}; },
    createElement() { return {textContent:'', get innerHTML() {
      return this.textContent.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }}; },
  },
  localStorage: {removeItem() {}},
});
vm.runInContext(source, context);
const result = vm.runInContext(`bars([['<img src=x onerror=alert(1)>', 1]])`, context);
assert(!result.includes('<img'));
assert(result.includes('&lt;img'));
assert(!html.includes('?token='));
assert(!html.includes('localStorage.setItem'));
console.log('PASS: analytics injected markup stays text; administrator token is not stored or sent in URL');
