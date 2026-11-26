import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const port=Number(process.env.PORT || 3210);
if(!Number.isInteger(port)||port<1024||port>65535) throw new Error('PORT must be an integer from 1024 to 65535.');
const url=`http://localhost:${port}`;
async function openBrowser(){
  console.log(`\nOpen your browser: ${url}\n`);
  if(process.platform==='win32' && process.env.YUESHI_NO_BROWSER!=='1') {
    await new Promise(resolve=>{
      const p=spawn('cmd.exe',['/d','/c','start','',url],{windowsHide:true,stdio:'ignore'});
      p.on('error',()=>{console.log('Browser launch failed. Open OPEN-WEB.url or copy the URL above.');resolve();});
      p.on('exit',code=>{if(code)console.log('Browser launch failed. Open OPEN-WEB.url or copy the URL above.');resolve();});
    });
  }
}
let running=false;
try { const r=await fetch(`${url}/api/status`,{signal:AbortSignal.timeout(1500)}); const s=await r.json();running=s.engine==='Pi SDK' && s.totalScenarios===20; } catch {}
if(running){console.log('YueShi is already running. This is normal, not an error.');await openBrowser();}
else {
  const child=spawn(process.execPath,['--env-file-if-exists=.env','server.mjs'],{cwd:root,stdio:['inherit','pipe','inherit'],windowsHide:true});
  let opened=false;
  child.stdout.on('data',chunk=>{process.stdout.write(chunk);if(!opened&&chunk.toString().includes('YueShi ready:')){opened=true;openBrowser();console.log('Keep this window open. Press Ctrl+C to stop.');}});
  child.on('error',error=>{console.error(error.message);process.exitCode=1;});
  child.on('exit',code=>{process.exitCode=code??0;});
  process.on('SIGINT',()=>{child.kill();process.exit();});
}
