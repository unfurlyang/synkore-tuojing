import {execFileSync} from 'node:child_process';
for(const args of [['scripts/prepare-app.mjs'],['scripts/run-framework.mjs','build']])execFileSync(process.execPath,args,{stdio:'inherit'});
