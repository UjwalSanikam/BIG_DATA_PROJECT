import {cp,mkdir,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
execFileSync('tar',['-czf','public/vm-kit.tar.gz','--exclude=__pycache__','-C','vm-kit','.'],{stdio:'inherit'});
await cp('database.sql','public/database.sql');
await rm('dist',{recursive:true,force:true});await mkdir('dist',{recursive:true});await cp('public','dist',{recursive:true});console.log('Built static dashboard. Vercel serves api/lab.mjs separately.');
