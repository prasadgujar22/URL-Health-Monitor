import asyncio
import pytest
from fastapi.testclient import TestClient
from app import store
from app.main import app, scheduler, next_deadline
from app.checker import validate_url, UnsafeURL, check, PinnedResolver

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
    for url in ['ftp://example.com','http://user:pass@example.com','http://127.0.0.1','http://[::1]','http://169.254.169.254','http://localhost','http://[::ffff:8.8.8.8]','http://224.0.0.1','http://[ff02::1]']:
        with pytest.raises(UnsafeURL): asyncio.run(validate_url(url))

def test_public_ipv6_literal_is_accepted():
    _, host, ips = asyncio.run(validate_url('https://[2001:4860:4860::8888]/'))
    assert host == '2001:4860:4860::8888' and ips == ['2001:4860:4860::8888']

@pytest.mark.asyncio
async def test_mixed_dns_answers_rejected(monkeypatch):
    async def answers(host,port,type):
        return [(None,None,None,None,('8.8.8.8',port)),(None,None,None,None,('10.0.0.1',port))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',answers)
    with pytest.raises(UnsafeURL): await validate_url('https://example.test')

@pytest.mark.asyncio
async def test_dns_rejects_mapped_and_multicast_answers(monkeypatch):
    for address in ('::ffff:8.8.8.8', '224.0.0.1', 'ff02::1'):
        async def answers(host,port,type,address=address):
            return [(None,None,None,None,(address,port))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',answers)
        with pytest.raises(UnsafeURL): await validate_url('https://public.example')

@pytest.mark.asyncio
async def test_reserved_ipv6_rejected_as_literal_and_dns_answer(monkeypatch):
    with pytest.raises(UnsafeURL):
        await validate_url('http://[4000::1]/')

    async def answers(host,port,type):
        return [(None,None,None,None,('4000::1',port))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',answers)
    with pytest.raises(UnsafeURL):
        await validate_url('https://reserved.example')

@pytest.mark.asyncio
async def test_mixed_public_and_reserved_dns_answers_rejected(monkeypatch):
    async def answers(host,port,type):
        return [(None,None,None,None,('8.8.8.8',port)),(None,None,None,None,('4000::1',port))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',answers)
    with pytest.raises(UnsafeURL):
        await validate_url('https://mixed.example')

@pytest.mark.asyncio
async def test_single_deadline_covers_dns_and_response(monkeypatch):
    async def slow_dns(*args, **kwargs):
        await asyncio.sleep(.04)
        return [(None,None,None,None,('8.8.8.8',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',slow_dns)
    import aiohttp
    class Response:
        status=200
        async def __aenter__(self):
            await asyncio.sleep(.04)
            return self
        async def __aexit__(self,*args): pass
    class Session:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        def get(self,*args,**kwargs): return Response()
    monkeypatch.setattr(aiohttp,'ClientSession',Session)
    result=await check('https://public.example',deadline_seconds=.06)
    assert result[0] is None and result[2:] == ('DOWN','timeout')

@pytest.mark.asyncio
async def test_http_classification_redirect_policy_and_proxy_bypass(monkeypatch):
    import aiohttp
    seen=[]
    async def validated(url):
        from urllib.parse import urlsplit
        return urlsplit(url),'public.example',['8.8.8.8']
    monkeypatch.setattr('app.checker.validate_url',validated)
    class Response:
        def __init__(self,code): self.status=code
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    class Session:
        def __init__(self,*args,**kwargs):
            assert kwargs['trust_env'] is False
            assert isinstance(kwargs['connector']._resolver,PinnedResolver)
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        def get(self,url,**kwargs):
            assert kwargs['allow_redirects'] is False
            return Response(seen[-1])
    monkeypatch.setattr(aiohttp,'ClientSession',Session)
    for code, expected in ((200,'UP'),(399,'UP'),(400,'DOWN'),(503,'DOWN')):
        seen.append(code)
        result=await check('https://public.example')
        assert result[0]==code and result[2]==expected

@pytest.mark.asyncio
async def test_pinned_resolver_rejects_hostname_switch():
    resolver=PinnedResolver('public.example',['8.8.8.8'])
    answer=await resolver.resolve('public.example',443)
    assert [x['host'] for x in answer]==['8.8.8.8']
    with pytest.raises(OSError): await resolver.resolve('private.example',443)

def test_pending_dashboard_does_not_add_empty_class_name():
    from pathlib import Path
    script=(Path(__file__).parents[1]/'app/static/app.js').read_text()
    assert "if(item.status==='UP')dot.classList.add('up');else if(item.status==='DOWN')dot.classList.add('down')" in script

def test_scheduler_uses_fixed_monotonic_ticks_and_skips_missed_batches():
    assert next_deadline(0, 10) == 60
    assert next_deadline(0, 60) == 120
    assert next_deadline(0, 145) == 180

@pytest.mark.asyncio
async def test_scheduler_controlled_clock_bounds_concurrency_and_skips_overrun(monkeypatch):
    items=[{'id':i,'url':f'https://target-{i}.example'} for i in range(10)]
    monkeypatch.setattr(store,'targets',lambda:items)
    clock={'now':0.0}
    calls=[]
    active=set()
    max_active=0
    second_sleep=asyncio.Event()
    sleeps=[]

    async def fake_check_one(item):
        nonlocal max_active
        ident=item['id']
        assert ident not in active, 'same target overlapped itself'
        active.add(ident)
        max_active=max(max_active,len(active))
        calls.append((clock['now'],ident))
        await asyncio.sleep(0)
        active.remove(ident)
        # Simulate the first full batch overrunning two 60-second ticks.
        if len(calls)==10:
            clock['now']=145.0
        if ident==3:
            raise RuntimeError('one target failed')

    async def controlled_sleep(delay):
        sleeps.append(delay)
        clock['now'] += delay
        if len(sleeps)==2:
            second_sleep.set()
            await asyncio.Future()

    monkeypatch.setattr('app.main.check_one',fake_check_one)
    task=asyncio.create_task(scheduler(clock=lambda:clock['now'],sleep=controlled_sleep))
    await asyncio.wait_for(second_sleep.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert len(calls)==20
    assert [at for at,_ in calls[:10]] == [0.0]*10
    assert [at for at,_ in calls[10:]] == [180.0]*10
    assert max_active == 8
    assert sleeps == [35.0,60.0]
    assert active == set()
