import asyncio
import pytest
from fastapi.testclient import TestClient
from app import store
from app.main import app, scheduler
from app.checker import validate_url, UnsafeURL

@pytest.fixture(autouse=True)
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',str(tmp_path/'monitor.db'))
    store.init()

def test_crud_duplicate_and_delete_cascades():
    with TestClient(app) as client:
        added=client.post('/api/urls',json={'url':'https://example.com'})
        assert added.status_code==201 and added.json()['status']=='PENDING'
        assert client.post('/api/urls',json={'url':'https://example.com'}).status_code==409
        ident=added.json()['id']; store.record(ident,200,12,'UP')
        assert len(client.get(f'/api/urls/{ident}/checks').json())==1
        assert client.delete(f'/api/urls/{ident}').status_code==204
        assert client.get(f'/api/urls/{ident}/checks').status_code==404

def test_checks_retain_newest_twenty():
    ident=store.add('https://example.com')
    for n in range(25): store.record(ident,200,n,'UP')
    rows=store.history(ident)
    assert len(rows)==20 and rows[0]['elapsed_ms']==24 and rows[-1]['elapsed_ms']==5

def test_rejects_credentials_and_nonpublic_addresses():
    for url in ['ftp://example.com','http://user:pass@example.com','http://127.0.0.1','http://[::1]','http://169.254.169.254','http://localhost']:
        with pytest.raises(UnsafeURL): asyncio.run(validate_url(url))

@pytest.mark.asyncio
async def test_mixed_dns_answers_rejected(monkeypatch):
    async def answers(host,port,type):
        return [(None,None,None,None,('8.8.8.8',port)),(None,None,None,None,('10.0.0.1',port))]
    monkeypatch.setattr(asyncio.AbstractEventLoop,'getaddrinfo',lambda self,*a,**kw: answers(*a,**kw))
    with pytest.raises(UnsafeURL): await validate_url('https://example.test')

@pytest.mark.asyncio
async def test_scheduler_continues_after_target_failure(monkeypatch):
    ids=[store.add('https://a.example'),store.add('https://b.example')]
    called=[]
    async def fake_check(url):
        called.append(url)
        if url.endswith('a.example'): raise RuntimeError('broken target')
        return (200,3,'UP',None)
    monkeypatch.setattr('app.main.check',fake_check)
    task=asyncio.create_task(scheduler())
    await asyncio.sleep(.15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert len(called)==2
    assert store.targets()[1]['status']=='UP'
