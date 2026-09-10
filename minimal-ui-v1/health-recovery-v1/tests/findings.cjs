const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..');
test('remote app merge never traverses inherited properties, including nested array records',()=>{
 const app=fs.readFileSync(path.join(root,'dist/app.js'),'utf8');
 const start=app.indexOf('  function updateStateObject('),end=app.indexOf('  window.DVIZH_MANUAL_STATE',start);
 const context=vm.createContext({});vm.runInContext(app.slice(start,end),context);
 for(const payload of ['{"__proto__":{"polluted":true}}','{"nested":{"constructor":{"prototype":{"polluted":true}}}}','{"rows":[{"id":"r","__proto__":{"polluted":true}}]}']){
  context.raw=payload;
  const result=vm.runInContext(`(()=>{const before=({}).polluted,target={nested:{},rows:[{id:'r'}]};updateStateObject(target,JSON.parse(raw));return {safe:({}).polluted===before,own:Object.hasOwn(target,'__proto__'),value:JSON.stringify(target)}})()`,context);
  assert.equal(result.safe,true,payload);
  assert.equal(result.value,payload);
 }
});
test('partial schedule confirmation resolves exact targets and before/after values',()=>{
 const ui=fs.readFileSync(path.join(root,'ui.js'),'utf8');
 const s=id=>({id,name:'Supplement '+id,dose:'old dose '+id,slots:[{id:'am',time:'08:00'},{id:'pm',time:'20:00'}],weekdays:[3],enabled:true});
 const context=vm.createContext({state:{healthRecovery:{schedules:{a:s('a'),b:s('b')}}},healthLabels:{},healthStatus:{}});
 vm.runInContext(ui.slice(ui.indexOf('function healthProposalDetail(')),context);
 const detail=id=>context.healthProposalDetail({action:'health_supplement_schedule',payload:{id,update:true,dose:'new dose',slots:[{id:'am',time:'09:00'}],weekdays:[4],day:'2026-09-10',timezone:'UTC'}});
 const a=detail('a'),b=detail('b');assert.notEqual(a,b);
 for(const value of ['Supplement a','a','am','pm','old dose a','new dose','08:00','09:00','20:00','Чт','Пт'])assert.ok(a.includes(value),value+' missing: '+a);
 const missing=detail('missing');assert.match(missing,/missing/);assert.doesNotMatch(missing,/Supplement [ab]|old dose/);
});
