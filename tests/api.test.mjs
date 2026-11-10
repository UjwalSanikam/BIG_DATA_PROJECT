import test,{after,before} from 'node:test';
import assert from 'node:assert/strict';
import {Readable} from 'node:stream';
import {mkdtemp,mkdir,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
let handler,room,tmp,original;
before(async()=>{original=process.cwd();await mkdir('.local',{recursive:true});tmp=await mkdtemp(path.join(original,'.local','test-'));process.chdir(tmp);process.env.LAB_LOCAL='1';({default:handler}=await import('../api/lab.mjs'));});
after(async()=>{process.chdir(original);await rm(tmp,{recursive:true,force:true});});
async function request(action,data,member='',invite=room?.invite){const req=Readable.from(data?[JSON.stringify(data)]:[]);req.url=`/api/lab?action=${action}`;req.method=data?'POST':'GET';req.headers={'content-type':'application/json','x-room-id':room?.id||'','x-room-key':invite||'','x-member-key':member};const res={statusCode:200,headers:{},setHeader(k,v){this.headers[k.toLowerCase()]=v;},end(value){this.data=value;}};await handler(req,res);return {status:res.statusCode,headers:res.headers,data:Buffer.isBuffer(res.data)?res.data:JSON.parse(res.data)};}
test('shared room auth, concurrent updates, evidence and persistence',async()=>{
 const create=await request('create',{title:'Test team'});assert.equal(create.status,201);room=create.data;
 assert.equal((await request('state',null,'','wrong')).status,403);
 assert.equal((await request('config',{config:{ip1:'10.1.1.1',ip2:'10.1.1.2',ip3:'10.1.1.3',ip4:'10.1.1.4',network:'aabbccddeeff0011',user:'ubuntu'}},room.owner)).status,200);
 const keys=[1,2,3,4].map(n=>'node-key-'+n+'-'.repeat(30));
 const joined=await Promise.all(keys.map((key,i)=>request('claim',{node:i+1,name:`Person ${i+1}`,key})));assert.ok(joined.every(r=>r.status===200));
 const completed=await Promise.all(keys.map((key,i)=>request('complete',{node:i+1,step:`n${i+1}-check`,confirm:true},key)));assert.ok(completed.every(r=>r.status===200));
 let current=(await request('state')).data;assert.equal(Object.keys(current.state.done).length,4);assert.equal(Object.keys(current.state.members).length,4);assert.ok(!JSON.stringify(current).includes('node-key-'));
 assert.equal((await request('complete',{node:1,step:'n1-install',confirm:true,note:'fake'},keys[0])).status,409);
 assert.equal((await request('note',{node:2,step:'n2-check',note:'pretend'},keys[0])).status,403);
 const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS9kAAAAASUVORK5CYII=';
 const uploaded=await request('evidence',{node:1,step:'n1-check',name:'terminal.png',mime:'image/png',data:png},keys[0]);assert.equal(uploaded.status,200);const id=uploaded.data.state.evidence['n1-check'][0].id;
 const image=await request(`image&id=${id}`);assert.equal(image.status,200);assert.equal(image.headers['content-type'],'image/png');assert.deepEqual(image.data,Buffer.from(png,'base64'));
 assert.equal((await request('evidence',{node:1,step:'n1-check',name:'bad.png',mime:'image/png',data:Buffer.from('not really an image at all').toString('base64')},keys[0])).status,400);
 const replay=await request('complete',{node:1,step:'n1-check',confirm:true},keys[0]);assert.equal(Object.keys(replay.data.state.done).length,4);
 assert.equal((await request('claim',{node:1,name:'Steal',key:'x'.repeat(30)})).status,409);
 // Locked instructions are withheld, not merely disabled in the UI.
 current=(await request('state')).data;
 assert.ok(current.state.stepContents['n1-check'].command);
 assert.ok(!current.state.stepContents['n1-install']);
 process.env.LAB_CREATE_KEY='test-owner-preview-password';
 const beforePreview=JSON.stringify(current);
 assert.equal((await request('preview',{step:'n1-install',password:process.env.LAB_CREATE_KEY},keys[0])).status,403);
 assert.equal((await request('preview',{step:'n1-install',password:'wrong'},room.owner)).status,403);
 assert.equal((await request('preview',{step:'n1-install'},room.owner)).status,403);
 const preview=await request('preview',{step:'n1-install',password:process.env.LAB_CREATE_KEY},room.owner);
 assert.equal(preview.status,200);assert.ok(preview.data.step.command);assert.ok(preview.data.step.expected);
 assert.equal(JSON.stringify((await request('state')).data),beforePreview);
 assert.equal((await request('complete',{node:1,step:'n1-install',confirm:true,note:'previewed'},keys[0])).status,409);
 assert.equal((await request('preview',null,room.owner)).status,405);
 assert.equal((await request('preview',{step:'unknown',password:process.env.LAB_CREATE_KEY},room.owner)).status,404);
 // Reopening an earlier checkpoint removes instructions from later responses.
 assert.ok(current.state.stepContents['n1-network']);
 await request('undo',{node:1,step:'n1-check',confirm:true},keys[0]);
 assert.ok(!(await request('state')).data.state.stepContents['n1-network']);
 delete process.env.LAB_CREATE_KEY;
});
