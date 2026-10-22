// Runs static/courier.html's real script in node against the live test server. Fake DOM only: this is NOT a browser render.
const fs=require('fs'),vm=require('vm');
const [,, base, token, scenario]=process.argv;
const html=fs.readFileSync(require('path').join(__dirname,'static','courier.html'),'utf8');
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const els={m:{innerHTML:''},ta:{value:''},tr:{value:''},tn:{value:''}};
const alerts=[];let confirmAns=true;
const ctx={document:{hidden:false,activeElement:{tagName:'BODY'},querySelectorAll:()=>[],getElementById:i=>els[i]||(els[i]={value:'',innerHTML:''})},localStorage:{getItem:()=>token||null},
 fetch:(u,o)=>fetch(base+u,o),alert:x=>alerts.push(x),confirm:()=>confirmAns,console,Promise,JSON,Math,String,parseFloat,Date,Set,navigator:{},setInterval:()=>0,setTimeout,clearTimeout};
vm.createContext(ctx);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 vm.runInContext(code+';this.__f={acc,adv,rel,topup,load}',ctx);await sleep(400);
 const out={};const html0=()=>els.m.innerHTML;
 const steps=JSON.parse(scenario||'[]');
 for(const st of steps){
  if(st.set)for(const k in st.set)els[k].value=st.set[k];
  if(st.confirm!==undefined)confirmAns=st.confirm;
  if(st.call)await ctx.__f[st.call](...(st.args||[]));
  await sleep(500);
  if(st.snap)out[st.snap]=html0();
 }
 out.alerts=alerts;out.final=html0();
 console.log(JSON.stringify(out));
})();
