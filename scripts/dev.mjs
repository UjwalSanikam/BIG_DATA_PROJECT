import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
process.env.LAB_LOCAL='1';const {default:api}=await import('../api/lab.mjs');
const root=path.resolve('public'),types={'.html':'text/html','.css':'text/css','.mjs':'text/javascript','.js':'text/javascript','.gz':'application/gzip','.json':'application/json','.svg':'image/svg+xml'};
const server=http.createServer(async(req,res)=>{if(req.url.startsWith('/api/lab'))return api(req,res);try{const requested=decodeURIComponent(new URL(req.url,'http://localhost').pathname);const file=path.resolve(root,'.'+(requested==='/'?'/index.html':requested));if(!file.startsWith(root+path.sep))throw Error();res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(await readFile(file));}catch{res.statusCode=404;res.end('Not found');}});
server.listen(Number(process.env.PORT||4173),'127.0.0.1',()=>console.log(`Local: http://127.0.0.1:${process.env.PORT||4173} — file-backed shared preview (not Vercel production)`));
