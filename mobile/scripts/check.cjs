const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'www'),config=require('../capacitor.config.json');
assert.equal(config.webDir,'www');assert.ok(!config.server.url);assert.equal(config.android.allowMixedContent,false);
for(const page of ['index.html','rewards.html','account-delete.html','privacy.html']){
  const html=fs.readFileSync(path.join(out,page),'utf8');assert.ok(html.includes('/static/native.js'),page);
  assert.ok(!html.includes('href="/my"'));assert.ok(!html.includes('href="/account/delete"'));
  for(const match of html.matchAll(/(?:src|href)="(\/static\/[^"?#]+)(?:[^" ]*)"/g))assert.ok(fs.existsSync(path.join(out,match[1])),match[1]);
}
for(const file of fs.readdirSync(out))assert.ok(!/admin|merchant|\.env|data|sqlite/i.test(file));
assert.ok(!fs.existsSync(path.join(out,'static','admin-auth.js')));
assert.ok(fs.readFileSync(path.join(out,'static','app.js'),'utf8').includes('!window.JustHereNative && "serviceWorker"'));
console.log('PASS: customer bundle, local routing, API bridge, private-tool exclusion and native SW guard. Not a device/build/signing test.');

const manifest=fs.readFileSync(path.join(root,'android/app/src/main/AndroidManifest.xml'),'utf8');
assert.ok(manifest.includes('android:allowBackup="false"'));assert.ok(manifest.includes('android:usesCleartextTraffic="false"'));assert.ok(manifest.includes('android.permission.ACCESS_COARSE_LOCATION'));
const plist=fs.readFileSync(path.join(root,'ios/App/App/Info.plist'),'utf8');for(const key of ['NSCameraUsageDescription','NSPhotoLibraryUsageDescription','NSLocationWhenInUseUsageDescription'])assert.ok(plist.includes(key));
const swift=fs.readFileSync(path.join(root,'ios/App/CapApp-SPM/Package.swift'),'utf8');assert.ok(!swift.split('\n').filter(x=>x.includes('.package(')).some(x=>x.includes('\\')),'Swift package paths use forward slashes');
console.log('PASS: native permissions, cleartext/Android backup disabled, portable iOS package paths');
