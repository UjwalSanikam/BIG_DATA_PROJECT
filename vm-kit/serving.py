"""Validate immutable exports and switch active.json atomically. No HDFS dependency."""
import hashlib, json, math, os, pathlib, shutil, sys, tarfile, tempfile, uuid
ROOT=pathlib.Path(__file__).resolve().parent
SERVING=ROOT/'serving'
def safe_version(value):
    if not isinstance(value,str) or not value or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in value):
        raise ValueError('Invalid version name')
    return value
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()
def atomic_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    with temp.open('w',encoding='utf-8') as f:
        json.dump(obj,f);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
def load_export(folder,check_hashes=True):
    import pyarrow.parquet as pq
    folder=pathlib.Path(folder).resolve()
    manifest=json.loads((folder/'manifest.json').read_text())
    safe_version(manifest['version'])
    if manifest['status']!='complete' or manifest['iterations']<10 or manifest['damping']!=.85 or manifest['k1']!=1.2 or manifest['b']!=.75:
        raise ValueError('Invalid export settings/status')
    if check_hashes:
        sums=json.loads((folder/'checksums.json').read_text())
        actual={str(p.relative_to(folder)).replace(os.sep,'/') for p in folder.rglob('*') if p.is_file() and p.name!='checksums.json'}
        if set(sums)!=actual: raise ValueError('Missing or unexpected export files')
        for name,sha in sums.items():
            path=(folder/name).resolve()
            if not path.is_relative_to(folder) or path.is_symlink() or digest(path)!=sha:
                raise ValueError('Checksum mismatch: '+name)
    rows={}
    for dataset in ('documents','postings','ranks'):
        if not (folder/dataset/'_SUCCESS').exists(): raise ValueError('Missing success marker')
        rows[dataset]=pq.read_table(folder/dataset).to_pylist()
    docs={x['doc_id']:x for x in rows['documents']}
    count=len(docs)
    if count!=len(rows['documents']) or count!=manifest['documents'] or count==0: raise ValueError('Invalid document coverage')
    ranks={x['doc_id']:x['pagerank'] for x in rows['ranks']}
    if len(ranks)!=len(rows['ranks']) or set(ranks)!=set(docs): raise ValueError('Invalid rank coverage')
    if any(not math.isfinite(v) or v<0 for v in ranks.values()) or abs(sum(ranks.values())-1)>1e-6: raise ValueError('Invalid PageRank mass')
    avgdl=sum(x['length'] for x in docs.values())/count
    if avgdl<=0 or abs(avgdl-manifest['avgdl'])>1e-6: raise ValueError('Invalid average document length')
    postings={};lengths={id:0 for id in docs}
    for row in rows['postings']:
        term,id,tf=row['term'],row['doc_id'],row['tf']
        if id not in docs or not isinstance(tf,int) or tf<=0 or not term: raise ValueError('Invalid posting')
        bucket=postings.setdefault(term,{})
        if id in bucket: raise ValueError('Duplicate posting')
        bucket[id]=tf;lengths[id]+=tf
    if len(rows['postings'])!=manifest['postings'] or any(lengths[id]!=docs[id]['length'] for id in docs): raise ValueError('Posting counts/lengths do not match')
    return dict(manifest=manifest,documents=docs,postings=postings,ranks=ranks,avgdl=avgdl)
def package(folder,archive):
    folder=pathlib.Path(folder)
    load_export(folder,check_hashes=False)
    sums={str(p.relative_to(folder)).replace(os.sep,'/'):digest(p) for p in folder.rglob('*') if p.is_file() and p.name!='checksums.json'}
    atomic_json(folder/'checksums.json',sums)
    load_export(folder)
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(folder.rglob('*')):
            tar.add(p,arcname=str(p.relative_to(folder)),recursive=False)
def activate(archive):
    SERVING.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='candidate-',dir=SERVING) as tmp:
        folder=pathlib.Path(tmp)
        with tarfile.open(archive,'r:gz') as tar:
            members=tar.getmembers()
            if sum(m.size for m in members)>500*1024*1024: raise ValueError('Export exceeds 500 MB serving limit')
            for member in members:
                if not (member.isfile() or member.isdir()) or not (folder/member.name).resolve().is_relative_to(folder): raise ValueError('Unsafe archive entry')
            tar.extractall(folder,members=members,filter='data')
        candidate=load_export(folder)
        meta=candidate['manifest']; version=safe_version(meta['version']); final=SERVING/version
        if final.exists():
            existing=load_export(final)
            if existing['manifest']!=meta or (final/'checksums.json').read_text()!=(folder/'checksums.json').read_text(): raise ValueError('Version collision')
        else:
            shutil.copytree(folder,final)
            load_export(final)
        pointer={'version':version,'phase':meta['phase'],'snapshot_id':meta['snapshot_id']}
        atomic_json(SERVING/f'phase{meta["phase"]}.json',pointer)
        atomic_json(SERVING/'active.json',pointer)
        print('ACTIVATE_OK',json.dumps(pointer))
def rollback(phase):
    pointer=json.loads((SERVING/f'phase{phase}.json').read_text())
    load_export(SERVING/safe_version(pointer['version']))
    atomic_json(SERVING/'active.json',pointer)
    print('ACTIVATE_OK',json.dumps(pointer))
def reject_test():
    active=SERVING/'active.json'; before=active.read_bytes();pointer=json.loads(before)
    with tempfile.TemporaryDirectory(prefix='bad-export-',dir=SERVING) as tmp:
        folder=pathlib.Path(tmp)/'candidate';shutil.copytree(SERVING/safe_version(pointer['version']),folder)
        part=next(folder.rglob('*.parquet'))
        with part.open('ab') as f:f.write(b'corrupted-test-candidate')
        try:load_export(folder)
        except ValueError:print('BAD_EXPORT_REJECTED')
        else:raise AssertionError('Corrupt export unexpectedly passed')
    assert active.read_bytes()==before,'Active version changed'
if __name__=='__main__':
    command=sys.argv[1]
    if command=='package':package(sys.argv[2],sys.argv[3])
    elif command=='activate':activate(sys.argv[2])
    elif command=='rollback':rollback(int(sys.argv[2]))
    elif command=='reject-test':reject_test()
    else:raise ValueError('Unknown command')
