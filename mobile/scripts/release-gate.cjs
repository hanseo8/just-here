const evidence=require('../release-evidence.json');
const missing=Object.entries(evidence).filter(([,value])=>value!==true).map(([key])=>key);
if(missing.length){console.error('STORE SUBMISSION BLOCKED — evidence missing:\n'+missing.map(x=>' - '+x).join('\n'));process.exitCode=1;}
else{console.log('Manual evidence recorded. Verify actual signed artifacts and reviewer requirements before submitting.');}
