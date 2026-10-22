import asyncio, ipaddress, socket, time
from urllib.parse import urlsplit
import aiohttp
from aiohttp.abc import AbstractResolver

class UnsafeURL(ValueError): pass

def _public_address(value):
    ip = ipaddress.ip_address(value)
    # Mapped IPv6 is rejected as a category, even when its embedded IPv4 is public.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return False
    return ip.is_global and not ip.is_multicast

async def validate_url(url):
    try:
        p=urlsplit(url)
        if p.scheme.lower() not in ('http','https') or not p.hostname or p.username is not None or p.password is not None: raise UnsafeURL('Enter a public HTTP or HTTPS URL without credentials.')
        if p.port is not None and not 1 <= p.port <= 65535: raise UnsafeURL('Invalid port.')
        host=p.hostname.rstrip('.').lower()
        try: ip=ipaddress.ip_address(host)
        except ValueError: ip=None
        if ip is not None:
            if not _public_address(ip): raise UnsafeURL('The destination must be a public address.')
            ips=[ip.compressed]
        else:
            if host in ('localhost','metadata.google.internal') or '.' not in host:
                raise UnsafeURL('Local and internal hostnames are not allowed.')
            loop=asyncio.get_running_loop()
            try:
                infos=await asyncio.wait_for(loop.getaddrinfo(host,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM),2)
            except asyncio.TimeoutError as e:
                # wait_for DNS deadline → unsafe. Outer check asyncio.timeout cancels the task — re-raise.
                task=asyncio.current_task()
                if task is not None and task.cancelling():
                    raise
                raise UnsafeURL('Could not resolve a public destination.') from e
            ips=list(dict.fromkeys(i[4][0] for i in infos))
            if not ips: raise UnsafeURL('The hostname has no address.')
        for value in ips:
            ip=ipaddress.ip_address(value)
            if not _public_address(ip): raise UnsafeURL('All destination addresses must be public.')
        return p,host,ips
    except (ValueError, UnicodeError) as e:
        if isinstance(e,UnsafeURL): raise
        raise UnsafeURL('Invalid URL.') from e
    except OSError as e: raise UnsafeURL('Could not resolve a public destination.') from e

class PinnedResolver(AbstractResolver):
    def __init__(self, host, ips): self.host=host; self.ips=ips
    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        if host.lower().rstrip('.') != self.host: raise OSError('Unexpected hostname')
        return [dict(hostname=host,host=ip,port=port,family=socket.AF_INET6 if ':' in ip else socket.AF_INET,proto=0,flags=socket.AI_NUMERICHOST) for ip in self.ips]
    async def close(self): pass

async def check(url, deadline_seconds=5):
    start=time.monotonic(); code=None; error=None
    try:
        async with asyncio.timeout(deadline_seconds):
            p,host,ips=await validate_url(url)
            resolver=PinnedResolver(host,ips)
            connector=aiohttp.TCPConnector(resolver=resolver,use_dns_cache=False,limit=1,ssl=True)
            timeout=aiohttp.ClientTimeout(total=5,connect=4,sock_read=4)
            async with aiohttp.ClientSession(connector=connector,timeout=timeout,trust_env=False) as session:
                async with session.get(url,allow_redirects=False,headers={'User-Agent':'URL-Health-Monitor/1.0'}) as response:
                    code=response.status
                    status='UP' if 200 <= code < 400 else 'DOWN'
                    return code,int((time.monotonic()-start)*1000),status,('http_error' if status=='DOWN' else None)
    except UnsafeURL: error='unsafe_destination'
    except asyncio.TimeoutError: error='timeout'
    except aiohttp.ClientConnectorCertificateError: error='tls_error'
    except aiohttp.ClientConnectorError: error='connection_error'
    except aiohttp.ClientError: error='network_error'
    except Exception: error='network_error'
    return code,int((time.monotonic()-start)*1000),'DOWN',error
