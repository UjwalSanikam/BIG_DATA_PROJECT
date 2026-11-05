import {mkdir,readFile,writeFile,rename} from 'node:fs/promises';
import path from 'node:path';
export class Store {
 constructor(){this.local=process.env.LAB_LOCAL==='1'&&!process.env.VERCEL;this.root=path.resolve('.local');}
 async rest(route,method='GET',body){
  const url=process.env.SUPABASE_URL,key=process.env.SUPABASE_SERVICE_ROLE_KEY;
  if(!url||!key)throw Object.assign(new Error('Shared storage is not configured. Add the Supabase server environment variables and run database.sql.'),{status:503});
  const r=await fetch(url.replace(/\/$/,'')+'/rest/v1/'+route,{method,headers:{apikey:key,...(key.startsWith('sb_secret_')?{}:{Authorization:`Bearer ${key}` }),'Content-Type':'application/json',Prefer:'return=representation'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(12000)});
  if(!r.ok)throw Object.assign(new Error('Shared storage request failed. Check database setup and server logs.'),{status:503});
  const t=await r.text();return t?JSON.parse(t):[];
 }
 async get(id){if(!this.local)return (await this.rest(`lab_rooms?id=eq.${id}&select=*`))[0];try{return JSON.parse(await readFile(path.join(this.root,id+'.json'),'utf8'));}catch(e){if(e.code==='ENOENT')return;throw e;}}
 async create(row){if(!this.local)return this.rest('lab_rooms','POST',row);await mkdir(this.root,{recursive:true});await writeFile(path.join(this.root,row.id+'.json'),JSON.stringify(row),{flag:'wx'});}
 async cas(id,version,state){
  if(!this.local)return (await this.rest(`lab_rooms?id=eq.${id}&version=eq.${version}`,'PATCH',{state,version:version+1})).length===1;
  // Local preview uses one Node process. Queue compare-and-swap operations across requests.
  const previous=this.queue||Promise.resolve();let release;this.queue=new Promise(r=>release=r);await previous;
  try{const old=await this.get(id);if(old.version!==version)return false;const file=path.join(this.root,id+'.json');await writeFile(file+'.tmp',JSON.stringify({...old,state,version:version+1}));await rename(file+'.tmp',file);return true;}finally{release();}
 }
 async putImage(row){if(!this.local)return this.rest('lab_evidence','POST',row);await mkdir(path.join(this.root,'evidence'),{recursive:true});await writeFile(path.join(this.root,'evidence',row.id+'.json'),JSON.stringify(row));}
 async image(id,room){if(!this.local)return (await this.rest(`lab_evidence?id=eq.${id}&room_id=eq.${room}&select=*`))[0];try{const row=JSON.parse(await readFile(path.join(this.root,'evidence',id+'.json'),'utf8'));return row.room_id===room?row:undefined;}catch(e){if(e.code==='ENOENT')return;throw e;}}
}
export const store=new Store();
