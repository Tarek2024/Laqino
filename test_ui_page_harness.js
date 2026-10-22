// Generic fake-DOM harness: runs a static page's real <script> in node against a live server. NOT a browser (no layout/CSS/real clicks).
// usage: node test_ui_page_harness.js <page> <base> <token> '<steps json>'   step: {js, prompt, confirm, snap}
const fs=require('fs'),vm=require('vm'),path=require('path');
const [,, page, base, token, stepsJson]=process.argv;
const html=fs.readFileSync(path.join(__dirname,'static',page+'.html'),'utf8');
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const els={};const el=i=>els[i]||(els[i]={value:'',innerHTML:'',textContent:'',hidden:false,className:''});
let promptAns=null,confirmAns=true;const alerts=[],errs=[];
const store=t=>({getItem:k=>(k==='t'||k==='at')?(token||null):(k==='rg'?'3':null),setItem(){},removeItem(){}});
const ctx={document:{hidden:false,activeElement:{tagName:'BODY'},querySelectorAll:()=>[],getElementById:el,body:{},addEventListener(){},querySelector:()=>el('q')},localStorage:store(),sessionStorage:store(),
 fetch:(u,o)=>fetch(base+u,o),alert:x=>alerts.push(String(x)),confirm:()=>confirmAns,prompt:()=>promptAns,console,Promise,JSON,Math,String,Date,Object,Array,parseFloat,setTimeout,clearTimeout,setInterval:()=>0,clearInterval:()=>{},Set,navigator:{},URL,location:{hash:'',pathname:'/'},history:{replaceState(){},pushState(){}},MutationObserver:class{observe(){}disconnect(){}}};
ctx.window=ctx;vm.createContext(ctx);
process.on('unhandledRejection',e=>errs.push(String(e)));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 try{vm.runInContext(code,ctx)}catch(e){errs.push('LOAD '+e)}
 await sleep(500);const out={};
 for(const st of JSON.parse(stepsJson||'[]')){
  if(st.prompt!==undefined)promptAns=st.prompt; if(st.confirm!==undefined)confirmAns=st.confirm;
  if(st.js){try{await vm.runInContext(st.js,ctx)}catch(e){errs.push('JS '+e)}}
  await sleep(st.wait||600);
  if(st.snap)out[st.snap+(st.as?'':'')]=el(st.snap).innerHTML||el(st.snap).textContent;
 }
 out.alerts=alerts;out.errs=errs;console.log(JSON.stringify(out));
})();
