// Minimal fake-DOM harness for static/market.html (createElement-based). NOT a browser: no layout/CSS. Runs the page's real <script> against a live server.
// usage: node test_market_dom_harness.js <base> <token|-> <hash> '<steps json>'   step: {js, wait}; helpers in page scope: $$click(textPart), $$find(textPart), $$tags(tag)
const fs=require('fs'),vm=require('vm'),path=require('path');
const [,, base, tokenArg, hash0, stepsJson]=process.argv; const token=tokenArg==='-'?'':tokenArg;
const html=fs.readFileSync(path.join(__dirname,'static','market.html'),'utf8');
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
class N{constructor(t){this.tag=t;this.children=[];this.attrs={};this.ls={};this._t='';this.style={};this.value='';this.disabled=false;this.scrollTop=0;this.scrollHeight=0;this.className='';this.maxlength=''}
 setAttribute(k,v){this.attrs[k]=v;if(k==='class')this.className=v;if(k==='value')this.value=v}
 appendChild(c){this.children.push(c);return c}
 addEventListener(e,f){(this.ls[e]=this.ls[e]||[]).push(f)}
 set textContent(v){this.children=[];this._t=String(v)} get textContent(){return this._t+this.children.map(c=>c.textContent).join('')}
 click(){(this.ls.click||[]).forEach(f=>f({}))}
 walk(f){f(this);this.children.forEach(c=>c.walk(f))}}
const els={};for(const m of html.matchAll(/id="([^"]+)"/g))els[m[1]]=new N('x');
const handlers=[];const loc={_h:hash0||'',get hash(){return this._h},set hash(v){this._h=v;setTimeout(()=>handlers.forEach(f=>f()),0)}};
const errs=[],timers=[];let promptAns=null;
const ctx={document:{hidden:false,title:'',getElementById:i=>els[i],createElement:t=>new N(t),createTextNode:t=>{const n=new N('#text');n._t=String(t);return n}},
 localStorage:{getItem:k=>k==='t'?(token||null):null,setItem(){},removeItem(){}},fetch:(u,o)=>fetch(base+u,o),location:loc,history:{length:1,back(){}},
 prompt:()=>promptAns,console,Promise,JSON,Math,String,Date,Object,Array,parseInt,parseFloat,Error,RegExp,Number,setTimeout,clearTimeout,
 setInterval:(f,ms)=>{timers.push(f);return timers.length},clearInterval:i=>{if(timers[i-1])timers[i-1]=null},encodeURIComponent,isNaN};
ctx.window=ctx;ctx.window.addEventListener=(e,f)=>{if(e==='hashchange')handlers.push(f)};ctx.window.scrollTo=()=>{};ctx.window.prompt=()=>promptAns;
ctx.$$find=t=>{let r=null;els.app.walk(n=>{if(!r&&n.ls.click&&n.textContent.includes(t))r=n});return r};
ctx.$$click=t=>{const n=ctx.$$find(t);if(!n)throw new Error('no clickable: '+t);n.click()};
ctx.$$tags=t=>{const o=[];els.app.walk(n=>{if(n.tag===t)o.push(n)});return o};
ctx.$$poll=()=>timers.forEach(f=>f&&f());
vm.createContext(ctx);process.on('unhandledRejection',e=>errs.push(String(e)));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{try{vm.runInContext(code,ctx)}catch(e){errs.push('LOAD '+e)}
 await sleep(500);const snaps=[];snaps.push(els.app.textContent);
 for(const st of JSON.parse(stepsJson||'[]')){if(st.prompt!==undefined)promptAns=st.prompt;try{await vm.runInContext(st.js||'0',ctx)}catch(e){errs.push('JS '+e.message)}await sleep(st.wait||500);snaps.push(els.app.textContent)}
 console.log(JSON.stringify({snaps,hash:loc._h,errs}))})();
