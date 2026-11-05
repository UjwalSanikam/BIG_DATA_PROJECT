import {createHash,randomBytes} from 'node:crypto';
import {steps,byId,blockers,cascade} from '../public/plan.mjs';
export const secret=()=>randomBytes(24).toString('base64url');
export const hash=s=>createHash('sha256').update(String(s||'')).digest('hex');
export function fail(message,status=400){throw Object.assign(new Error(message),{status});}
export function sanitize(state){const s=structuredClone(state);delete s.owner;for(const n of Object.values(s.members))delete n.key;return s;}
export function configure(c){
 const out={};for(const key of ['ip1','ip2','ip3','ip4']){const ip=String(c[key]||'');if(ip&&(!/^(\d{1,3}\.){3}\d{1,3}$/.test(ip)||ip.split('.').some(v=>+v>255)))fail('Enter valid ZeroTier IPv4 addresses, or leave them blank until devices join.');out[key]=ip;}
 const filled=Object.values(out).filter(Boolean);if(new Set(filled).size!==filled.length)fail('Each VM needs a different address.');
 if(!/^[0-9a-f]{16}$/i.test(c.network||''))fail('ZeroTier network IDs contain 16 hexadecimal characters.');
 if(!/^[a-z_][a-z0-9_-]{0,30}$/.test(c.user||''))fail('Use a valid Linux username, identical on every VM.');
 return {...out,network:c.network.toLowerCase(),user:c.user};
}
export function mutate(state,action,b,token){
 const s=structuredClone(state);const node=Number(b.node),member=s.members[node],isOwner=hash(token)===s.owner;
 const event=(text)=>{s.activity.unshift({text,at:new Date().toISOString()});s.activity=s.activity.slice(0,150);};
 if(action==='claim'){
  if(![1,2,3,4].includes(node))fail('Choose a VM.');if(member)fail('This VM is already assigned. Use its saved recovery key or ask the room owner to release the seat.',409);
  const name=String(b.name||'').trim().slice(0,40);if(!name)fail('Enter your name.');if(typeof b.key!=='string'||b.key.length<24)fail('Invalid member key.');
  s.members[node]={name,key:hash(b.key),joined:new Date().toISOString()};event(`${name} joined Node ${node}.`);return s;
 }
 if(action==='config'){if(!isOwner)fail('Only the team owner can change setup.',403);if(Object.keys(s.done).some(id=>id.endsWith('-configure')))fail('Settings are locked after a VM saves its addresses. Reopen those steps to edit the network configuration.',409);s.config=configure(b.config);event('Team network settings saved.');return s;}
 if(action==='release'){if(!isOwner)fail('Only the room owner can release a seat.',403);if(member){delete s.members[node];event(`Node ${node} seat released; its work is retained.`);}return s;}
 if(!member||hash(token)!==member.key)fail('Only the assigned teammate can update this VM.',403);
 const step=byId[b.step];if(!step||step.node!==node)fail('That step belongs to another VM.',403);
 if(action==='complete'){
  if(s.done[step.id])return s;
  if(step.id.endsWith('-network')&&!s.config?.network)fail('The room owner must save the ZeroTier network ID in Team settings first.');
  if(step.id.endsWith('-configure')&&![1,2,3,4].every(n=>s.config?.[`ip${n}`]))fail('Save all four private IP addresses in Team settings first.');
  if(blockers(step,s.done).length)fail('Complete the prerequisite steps first.',409);
  if(b.confirm!==true)fail('Confirm that you compared your output with the expected result.');
  if(step.evidence&&!s.evidence[step.id]?.length&&!String(b.note||'').trim())fail('This checkpoint needs a screenshot or pasted output.');
  s.done[step.id]={at:new Date().toISOString(),by:member.name,note:String(b.note||'').slice(0,6000)};event(`${member.name} completed ${step.title}.`);
 }else if(action==='undo'){
  if(b.confirm!==true)fail('Confirm reopening dependent steps.');const ids=cascade(step.id,s.done);for(const id of ids)delete s.done[id];event(`${member.name} reopened ${step.title} and ${Math.max(0,ids.length-1)} dependent steps. Evidence is retained.`);
 }else if(action==='evidence'){
  const list=s.evidence[step.id]||[];if(list.length>=3)fail('Maximum three screenshots per step.');list.push(b.image);s.evidence[step.id]=list;event(`${member.name} added evidence to ${step.title}.`);
 }else if(action==='note'){
  s.notes[step.id]={text:String(b.note||'').slice(0,6000),by:member.name,at:new Date().toISOString()};event(`${member.name} updated a note on ${step.title}.`);
 }else fail('Unknown action.');return s;
}
