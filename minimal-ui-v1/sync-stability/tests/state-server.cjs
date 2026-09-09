// Synthetic /api/state contract shared by browser and deterministic cache tests.
const copy=value=>JSON.parse(JSON.stringify(value));
function stateServer(state,{cas=true}={}) {
 return {state:copy(state),revision:10,request(method,body){
  let status=200;
  if(method==='PUT') {
   if(cas && body.baseRevision!==this.revision) status=409;
   else {this.state=copy(body.state);this.revision++;}
  }
  return {status,body:copy({state:this.state,revision:this.revision})};
 }};
}
module.exports={stateServer};
