// Capacitor CLI on Windows emits backslashes in SPM package paths; Swift needs '/'.
const fs=require('node:fs'),path=require('node:path');
const file=path.resolve(__dirname,'../ios/App/CapApp-SPM/Package.swift');
if(fs.existsSync(file))fs.writeFileSync(file,fs.readFileSync(file,'utf8').split('\n').map(line=>line.includes('.package(')?line.replaceAll('\\','/'):line).join('\n'));
