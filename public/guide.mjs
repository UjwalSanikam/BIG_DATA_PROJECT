import {steps,byId} from './plan.mjs';
const escape=v=>String(v).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function render(){const node=Number(document.querySelector('#node').value);document.querySelector('#guide').innerHTML=steps.filter(s=>s.node===node).map((s,i)=>'<section class="panel"><h2>'+s.stage+' · '+(i+1)+'. '+escape(s.title)+'</h2><p>Open your shared workspace to view instructions after prerequisites are complete.</p>'+(s.deps.length?'<div class="callout red"><strong>Prerequisites</strong>'+s.deps.map(id=>'Node '+byId[id].node+': '+escape(byId[id].title)).join('<br>')+'</div>':'')+'</section>').join('');}
document.querySelector('#node').addEventListener('change',render);render();
