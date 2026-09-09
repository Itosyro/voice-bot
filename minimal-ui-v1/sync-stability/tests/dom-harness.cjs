const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM,VirtualConsole}=require(process.env.JSDOM_PATH || 'jsdom');
const {fixture,copy,T0}=require('./harness.cjs');
const {stateServer}=require('./state-server.cjs');
async function domHarness(customize = () => {}, versions = {app:'release',sync:'release'}) {
 const root=path.join(__dirname,'..');
 const navigationErrors=[],virtualConsole=new VirtualConsole();
 virtualConsole.on('jsdomError',error=>{
  if(error.type==='not-implemented' && /navigation/.test(error.message)) navigationErrors.push(error.message);
  else if(error.type!=='unhandled-exception') throw error;
 });
 const dom=new JSDOM(fs.readFileSync(path.join(root,versions.sync,'manual.html'),'utf8'),{url:'http://dvizh.test/manual.html?v=20260909-sync-stability-2',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole});
 const w=dom.window; const timers=new Map(); let id=0,now=0,remote=fixture(); const requests=[],errors=[];
 Object.assign(remote,{tone:'direct',focusDuration:8,selectedFocusTaskId:'synthetic-task'});
 Object.assign(remote.tasks[0],{micro:'Base micro',area:'Разное',duration:8,energy:1,fear:0,priority:2,done:false});
 customize(remote);
 const service=versions.service || stateServer(remote);
 const schedule=(fn,ms,interval=false)=>{const key=++id;timers.set(key,{fn,at:now+Number(ms||0),ms:Number(ms||0),interval});return key;};
 w.setTimeout=(fn,ms)=>schedule(fn,ms);w.setInterval=(fn,ms)=>schedule(fn,ms,true);w.clearTimeout=w.clearInterval=key=>timers.delete(key);
 w.requestAnimationFrame=fn=>schedule(fn,16);w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};
 w.Date=class extends Date {constructor(...args){super(...(args.length?args:[Date.parse(T0)+now]));}static now(){return Date.parse(T0)+now;}};
 w.addEventListener('error',e=>errors.push(e.error));
 w.fetch=async(url,options={})=>{
  if(url!=='/api/state') throw Error('Unexpected URL');
  requests.push({method:options.method||'GET',body:options.body&&JSON.parse(options.body)});
  const result=service.request(options.method||'GET',options.body&&JSON.parse(options.body));
  return {ok:result.status===200,status:result.status,json:async()=>result.body};
 };
 const run=name=>vm.runInContext(fs.readFileSync(path.join(root,name==='app.js'?versions.app:name==='sync.js'?versions.sync:'baseline',name),'utf8'),dom.getInternalVMContext(),{filename:name});
 const append=w.document.body.appendChild.bind(w.document.body);
 w.document.body.appendChild=node=>{const result=append(node);if(node.tagName==='SCRIPT'){run('app.js');node.dispatchEvent(new w.Event('load'));}return result;};
 const flush=async()=>{for(let i=0;i<50;i++)await Promise.resolve();};
 for(const [key,value] of Object.entries(versions.storage || {})) w.localStorage.setItem(key,value);
 versions.beforeSync?.(w);
 run('sync.js');versions.beforeReady?.(w);await w.DVIZH_SYNC_READY;
 await versions.beforeBoot?.(w,flush);
 run('boot.js');await flush();
 const advance=async ms=>{const end=now+ms;for(;;){const entry=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!entry)break;const [key,t]=entry;now=t.at;if(t.interval)t.at+=t.ms;else timers.delete(key);t.fn();await flush();}now=end;await flush();};
 const click=selector=>{const el=w.document.querySelector(selector);if(!el)throw Error(`Missing ${selector}`);el.click();};
 return {w,dom,requests,errors,navigationErrors,advance,flush,click,remote:()=>copy(service.state),pull:async change=>{service.state=copy(service.state);change(service.state);service.revision++;await w.DVIZH_SYNC.pull();await flush();},state:()=>JSON.parse(w.localStorage.getItem('dvizh-state-v1'))};
}
module.exports={domHarness};
