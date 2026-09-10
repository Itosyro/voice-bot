const vm=require('node:vm'),fs=require('node:fs');
const ctx={window:{},Intl,Date,crypto:require('node:crypto').webcrypto};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../domain.js'),'utf8'),ctx);
let input='';process.stdin.on('data',b=>input+=b);process.stdin.on('end',()=>{
 const {state,actions,day}=JSON.parse(input);let errors=[];
 for(const [action,payload]of actions){try{ctx.window.DVIZH_HEALTH.apply(state,action,payload);errors.push(false)}catch{errors.push(true)}}
 console.log(JSON.stringify({state,summary:ctx.window.DVIZH_HEALTH.summary(state,day),errors}));
});
