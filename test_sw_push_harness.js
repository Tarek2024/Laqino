// Runs static/sw.js's real push / notificationclick handlers in a vm with a fake ServiceWorkerGlobalScope. NOT a browser (no real Push service).
// prints JSON: one result per scenario {name, shown:[{title,tag,silent,url,requireInteraction}], closed:n}
const fs=require('fs'),vm=require('vm'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'static','sw.js'),'utf8');
async function run(sc){
  const handlers={},store=new Map(),shown=[],live=[];let closed=0,opened=null,focused=null;
  const caches={open:async()=>({match:async k=>store.get(k),put:async(k,v)=>{store.set(k,v)}}),keys:async()=>[],delete:async()=>true};
  if(sc.meta)store.set('/__laqino_meta',new Response(JSON.stringify(sc.meta)));
  const mk=(title,o)=>{const n={title,...o,close(){closed++}};live.push(n);shown.push({title,tag:o&&o.tag,silent:!!(o&&o.silent),url:o&&o.data&&o.data.url,requireInteraction:!!(o&&o.requireInteraction)})};
  const self={addEventListener:(t,f)=>{handlers[t]=f},registration:{pushManager:{getSubscription:async()=>sc.noSub?null:{endpoint:'https://push.example/e1'}},showNotification:async(t,o)=>mk(t,o),getNotifications:async()=>live.splice(0)},
    clients:{matchAll:async()=>sc.windows||[],openWindow:async u=>{opened=u},claim:async()=>{}},skipWaiting(){}};
  const ctx={self,caches,Response,URL,JSON,Promise,Math,String,Object,Array,Date,console,location:{origin:'https://app.example'},setTimeout:f=>{f();return 0},
    fetch:async(u,o)=>{if(String(u).includes('/api/push/state')){if(sc.state==='fail')throw new Error('offline');return {ok:true,json:async()=>sc.state}}return {ok:false}}};
  vm.createContext(ctx);vm.runInContext(code,ctx);
  if(sc.click){let p;handlers.notificationclick({notification:{close(){closed++},data:sc.click},waitUntil:x=>{p=x}});await p;return {name:sc.name,opened,focused:focused}}
  let p;handlers.push({waitUntil:x=>{p=x}});await p;return {name:sc.name,shown,closed};
}
(async()=>{const S=JSON.parse(process.argv[2]);const out=[];for(const sc of S)out.push(await run(sc));console.log(JSON.stringify(out))})();
