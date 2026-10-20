const fs=require('node:fs/promises'),path=require('node:path'),esbuild=require('esbuild');
const root=path.resolve(__dirname,'../..'),out=path.resolve(__dirname,'../www');
const pages=['index.html','rewards.html','account-delete.html','privacy.html'];
const assets=['styles.css','app.js','auth.js','wallet.js','payouts.js','rewards.css','instagram.js','instagram-places.json','badges.js','story.js','food-categories.json'];
const folders=['icons','badges','brand','tastes'];
(async()=>{
  // Generated customer bundle only. This exact target is fixed inside mobile/.
  if(out!==path.join(root,'mobile','www'))throw Error('Unexpected output directory');
  await fs.rm(out,{recursive:true,force:true});
  await fs.mkdir(path.join(out,'static'),{recursive:true});
  const routes=[['/static/privacy.html','/privacy.html'],['/account/delete','/account-delete.html'],['/my','/rewards.html'],['/rewards','/rewards.html']];
  function rewrite(text){for(const [from,to] of routes)text=text.replaceAll('href="'+from+'"','href="'+to+'"');return text.replaceAll('href="/"','href="/index.html"');}
  for(const page of pages){let html=await fs.readFile(path.join(root,'web',page),'utf8');html=rewrite(html).replace('<head>','<head><script src="/static/native.js"></script>');
    await fs.writeFile(path.join(out,page),html);
  }
  await fs.copyFile(path.join(root,'web/manifest.webmanifest'),path.join(out,'manifest.webmanifest'));
  for(const file of assets){let data=await fs.readFile(path.join(root,'web',file));if(file.endsWith('.js')){let text=rewrite(data.toString());if(file==='app.js')text=text.replace('if ("serviceWorker" in navigator)', 'if (!window.JustHereNative && "serviceWorker" in navigator)').replace('const url = String(card.image_url || "").trim();','const url = window.JustHereNative.remoteUrl(String(card.image_url || "").trim());').replaceAll('${location.origin}', '${window.JustHereNative.apiBase}');data=Buffer.from(text)}await fs.writeFile(path.join(out,'static',file),data);}
  for(const folder of folders)await fs.cp(path.join(root,'web',folder),path.join(out,'static',folder),{recursive:true});
  await esbuild.build({entryPoints:[path.join(root,'mobile/src/native.js')],bundle:true,format:'iife',platform:'browser',target:'es2022',outfile:path.join(out,'static/native.js')});
  console.log('Customer native bundle built: no admin, merchant, data, or secrets.');
})().catch(e=>{console.error(e);process.exitCode=1});
