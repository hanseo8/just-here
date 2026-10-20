const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
vm.runInThisContext(fs.readFileSync('web/wallet.js','utf8'));
assert.deepEqual(JustHereWallet.summarize({balance:300,pending_points:300,payouts:[{status:'pending',amount_krw:300},{status:'processing',amount_krw:300},{status:'paid',amount_krw:300},{status:'rejected',amount_krw:300}]}),{available:300,pending:300,reserved:600,paid:300});
assert.deepEqual(JustHereWallet.summarize({}),{available:0,pending:0,reserved:0,paid:0});
const html=fs.readFileSync('web/rewards.html','utf8');for(const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))if(m[1].trim())new vm.Script(m[1]);
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size);
console.log('PASS: wallet holds are not deducted twice; paid/rejected separated; empty totals; inline syntax; unique IDs');
