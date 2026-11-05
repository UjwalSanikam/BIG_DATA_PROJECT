import {randomUUID} from 'node:crypto';
import {store} from '../lib/store.mjs';
import {hash,secret,fail,mutate,sanitize} from '../lib/domain.mjs';
const uuid=/^[a-f0-9-]{36}$/;
async function body(req){if(req.body)return typeof req.body==='string'?JSON.parse(req.body):req.body;let text='';for await(const chunk of req){text+=chunk;if(text.length>1550000)fail('Upload is too large. Use a screenshot under 1 MB.',413);}return text?JSON.parse(text):{};}
export default async function handler(req,res){
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
 const send=(code,data)=>{res.statusCode=code;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));};
 try{
  const url=new URL(req.url,'http://localhost'),action=url.searchParams.get('action')||'state';
  if(action==='health'){if(!['GET','HEAD'].includes(req.method))fail('Method not allowed',405);return send(200,{mode:store.local?'local':'shared',configured:store.local||!!(process.env.SUPABASE_URL&&process.env.SUPABASE_SERVICE_ROLE_KEY&&process.env.LAB_CREATE_KEY)});}
  if(!['GET','POST'].includes(req.method))fail('Method not allowed',405);
  if(req.method==='GET'&&!['state','image'].includes(action))fail('Use POST for changes.',405);
  const b=req.method==='POST'?await body(req):{};
  if(action==='create'){
   if(!store.local&&(!process.env.LAB_CREATE_KEY||hash(b.createKey)!==hash(process.env.LAB_CREATE_KEY)))fail('Enter the team creation key configured by the website owner.',403);
   const id=randomUUID(),invite=secret(),owner=secret();const state={title:String(b.title||'Distributed Search Engine').trim().slice(0,70),owner:hash(owner),members:{},config:null,done:{},evidence:{},notes:{},activity:[{text:'Workspace created. Invite your team and configure the four VMs.',at:new Date().toISOString()}]};
   await store.create({id,invite_hash:hash(invite),version:0,state});return send(201,{id,invite,owner,state:sanitize(state),version:0});
  }
  const id=req.headers['x-room-id'];if(!uuid.test(id||''))fail('Invalid workspace.',400);
  const row=await store.get(id);if(!row||hash(req.headers['x-room-key'])!==row.invite_hash)fail('Workspace or invitation key is invalid.',403);
  if(action==='state')return send(200,{state:sanitize(row.state),version:row.version});
  if(action==='image'){
   const imageId=url.searchParams.get('id');if(!uuid.test(imageId||''))fail('Invalid image.');const image=await store.image(imageId,id);if(!image)fail('Screenshot not found.',404);
   res.setHeader('Content-Type',image.mime);res.end(Buffer.from(image.data,'base64'));return;
  }
  const token=req.headers['x-member-key']||'';
  if(action==='evidence'){
   // Authorize the seat and step before storing anything.
   mutate(row.state,'note',{...b,note:''},token);
   if((row.state.evidence[b.step]||[]).length>=3)fail('Maximum three screenshots per step.');
   if(!['image/png','image/jpeg','image/webp'].includes(b.mime)||typeof b.data!=='string'||!/^[A-Za-z0-9+/]*={0,2}$/.test(b.data))fail('Choose a PNG, JPEG or WebP screenshot.');
   const bytes=Buffer.from(b.data,'base64');if(bytes.length>1048576||bytes.length<12)fail('Screenshot must be between 12 bytes and 1 MB.');
   const valid=b.mime==='image/png'?bytes.subarray(0,8).equals(Buffer.from('89504e470d0a1a0a','hex')):b.mime==='image/jpeg'?bytes[0]===255&&bytes[1]===216&&bytes[2]===255:bytes.toString('ascii',0,4)==='RIFF'&&bytes.toString('ascii',8,12)==='WEBP';if(!valid)fail('File contents do not match the selected image type.');
   const image={id:randomUUID(),name:String(b.name||'Screenshot').slice(0,100),at:new Date().toISOString()};
   await store.putImage({...image,room_id:id,step_id:b.step,mime:b.mime,data:b.data});b.image=image;
  }
  for(let attempt=0;attempt<6;attempt++){
   const current=attempt?await store.get(id):row;const next=mutate(current.state,action,b,token);
   if(await store.cas(id,current.version,next))return send(200,{state:sanitize(next),version:current.version+1});
  }
  fail('A teammate updated this workspace at the same moment. Please retry.',409);
 }catch(e){if(!e.status)console.error('SearchLab server error:',e.code||e.name,e.message);send(e.status||500,{error:e.status?e.message:'The server could not finish this request. Retry without marking the step done.'});}
}
