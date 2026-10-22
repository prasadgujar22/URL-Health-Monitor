import asyncio, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import store
from .checker import check, validate_url, UnsafeURL

async def check_one(target):
    try: result=await asyncio.wait_for(check(target['url']),timeout=5.1)
    except asyncio.TimeoutError: result=(None,5000,'DOWN','timeout')
    store.record(target['id'],*result)

async def scheduler():
    while True:
        batch=store.targets()
        sem=asyncio.Semaphore(8)
        async def bounded(item):
            async with sem: await check_one(item)
        await asyncio.gather(*(bounded(x) for x in batch),return_exceptions=True)
        await asyncio.sleep(max(0,60))

@asynccontextmanager
async def lifespan(app):
    store.init()
    task=asyncio.create_task(scheduler())
    app.state.scheduler=task
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app=FastAPI(title='URL Health Monitor',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=os.path.join(os.path.dirname(__file__),'static')),name='static')
class URLInput(BaseModel): url:str
@app.get('/')
def index(): return FileResponse(os.path.join(os.path.dirname(__file__),'static','index.html'))
@app.get('/healthz')
def health(): return {'status':'ok'}
@app.get('/api/urls')
def list_urls(): return store.targets()
@app.post('/api/urls',status_code=201)
async def create_url(payload:URLInput):
    url=payload.url.strip()
    try: await validate_url(url)
    except UnsafeURL as e: raise HTTPException(422,str(e))
    ident=store.add(url)
    if ident is None: raise HTTPException(409,'This URL is already being monitored.')
    return {'id':ident,'url':url,'status':'PENDING','http_code':None,'elapsed_ms':None,'checked_at':None,'error':None}
@app.delete('/api/urls/{target_id}',status_code=204)
def remove_url(target_id:int):
    if not store.delete(target_id): raise HTTPException(404,'URL not found.')
@app.get('/api/urls/{target_id}/checks')
def get_checks(target_id:int):
    if not any(t['id']==target_id for t in store.targets()): raise HTTPException(404,'URL not found.')
    return store.history(target_id)
