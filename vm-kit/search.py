import json, threading
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from serving import ROOT, SERVING, load_export, safe_version
from ranking import score
app=FastAPI(title='SearchLab search',version='1.0.0')
lock=threading.Lock(); loaded=None; stamp=None; warning=None
def current():
    global loaded, stamp, warning
    with lock:
        try:
            path=SERVING/'active.json'; signature=path.read_bytes()
            if signature!=stamp:
                pointer=json.loads(signature)
                candidate=load_export(SERVING/safe_version(pointer['version']))
                loaded=candidate;stamp=signature;warning=None
        except Exception as e:
            warning='Candidate unavailable or invalid; retained the last validated version.'
        return loaded
@app.get('/')
def home():return FileResponse(ROOT/'search-ui.html')
@app.get('/health')
def health():
    data=current()
    if data is None:return JSONResponse({'ready':False,'message':'No validated export is active yet.'},status_code=503)
    m=data['manifest']
    return {'ready':True,'version':m['version'],'snapshot_id':m['snapshot_id'],'documents':m['documents'],'warning':warning}
@app.get('/search')
def search(q:str=Query(min_length=1,max_length=300),limit:int=Query(default=10,ge=1,le=50)):
    data=current()
    if data is None:return JSONResponse({'error':'No validated export is active yet.'},status_code=503)
    return {'query':q,'version':data['manifest']['version'],'snapshot_id':data['manifest']['snapshot_id'],
            'results':score(q,data['documents'],data['postings'],data['ranks'],data['avgdl'],limit)}
