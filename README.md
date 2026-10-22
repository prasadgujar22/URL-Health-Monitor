# URL Health Monitor

A small self-hosted URL monitor: one FastAPI process serves an accessible responsive dashboard and JSON API, while SQLite stores targets and the newest 20 checks per target. This MVP has **no authentication**; run it only on a trusted machine or behind an access-controlled network boundary.

## Local setup

Requires Python 3.12 or newer.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The database defaults to `./data/monitor.db`; set `DATABASE_PATH` to change it. Persist that file to retain targets and history across restarts. The scheduler checks existing targets immediately at startup and approximately every 60 seconds; no manual check button is needed. A new target is shown as pending until the first check completes.

## API

- `GET /api/urls` returns an array of `{id,url,created_at,http_code,elapsed_ms,checked_at,status,error}`; result fields are null while pending.
- `POST /api/urls` accepts `{"url":"https://example.com"}` and returns the created target (201). Duplicate URLs return 409; invalid or unsafe URLs return 422 with a detail message.
- `DELETE /api/urls/{id}` deletes the URL and its check history (204); unknown IDs return 404.
- `GET /api/urls/{id}/checks` returns up to 20 results, newest first.
- `GET /healthz` returns `{"status":"ok"}`.

HTTP 200–399 means UP; 400–599 means DOWN. Timeouts, DNS, TLS, and connection failures are DOWN with no HTTP code. Each check has a five-second deadline and reads no response body. Per-target records retain UTC check time and elapsed milliseconds.

## SSRF protections

Only HTTP(S), syntactically valid public hosts are accepted; credentials and local/internal names are rejected. Before every request the monitor resolves the hostname and rejects the entire answer set if any address is non-public (including private, loopback, link-local, reserved, multicast, unspecified, IPv4-mapped IPv6, and metadata addresses). The HTTP connector uses only that validated address set while retaining the original hostname for Host and TLS certificate/SNI checks. Redirect following and environment proxies are disabled. DNS and connections are subject to bounded timeouts and concurrency.

## Tests

```sh
python -m pip install -e '.[test]'
python -m pytest -q
```

The regression suite covers CRUD, duplicates, cascade deletion, 20-result retention, unsafe and mixed DNS answers, and scheduler fault isolation. Docker and Actions integration are a separate DevOps handoff.
