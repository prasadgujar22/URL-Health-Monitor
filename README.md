# URL Health Monitor

A self-hosted URL monitor: one FastAPI process serves an accessible, responsive dashboard and JSON API, while SQLite stores targets and the newest 20 checks per target. This MVP has **no authentication**. Run it only on a trusted machine or behind an access-controlled network boundary.

## Run with Docker

Build the image and create a persistent named volume:

```sh
docker build -t url-health-monitor .
docker volume create url-monitor-data
docker run -d --name url-health-monitor \
  -p 127.0.0.1:8000:8000 \
  -v url-monitor-data:/data \
  url-health-monitor
```

Open <http://127.0.0.1:8000>. The container runs `app.main:app` on port 8000 with one Uvicorn worker and stores SQLite at `/data/monitor.db`. The named volume preserves targets and check history across container replacement. To stop and remove the container while retaining its data, run `docker rm -f url-health-monitor`; start a replacement with the same volume.

## Run locally

Requires Python 3.12 or newer.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
DATABASE_PATH=./data/monitor.db uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open <http://127.0.0.1:8000>. `DATABASE_PATH` defaults to `./data/monitor.db`; choose a persistent writable path to retain data. The scheduler checks stored targets immediately at startup and approximately every 60 seconds. New targets show pending until their first result is recorded.

## Dashboard and API

The dashboard supports adding and deleting monitors, reports duplicate submissions, and displays pending, status, response code, response time and check time.

- `GET /api/urls` returns an array of `{id,url,created_at,http_code,elapsed_ms,checked_at,status,error}`; result fields are null while pending.
- `POST /api/urls` accepts `{"url":"https://example.com"}` and returns the created target (201). Duplicate URLs return 409; invalid or unsafe URLs return 422 with a detail message.
- `DELETE /api/urls/{id}` deletes the URL and its check history (204); unknown IDs return 404.
- `GET /api/urls/{id}/checks` returns up to 20 results, newest first.
- `GET /healthz` returns `{"status":"ok"}`.

HTTP 200–399 means UP; HTTP 400–599 means DOWN. Timeouts, DNS, TLS and connection failures are DOWN with a null HTTP code and a safe error category. Checks have a five-second deadline and do not download response bodies. Timestamps are UTC and elapsed times are milliseconds.

## SSRF policy

Only HTTP(S) URLs with a valid public host are accepted. Credentials and local/internal names are rejected. Before every request the monitor resolves the hostname and rejects the entire answer set if any address is non-public, including private, loopback, link-local, reserved, multicast, unspecified, IPv4-mapped IPv6 and metadata addresses. The HTTP connector connects only to the validated address set while retaining the original hostname for Host and TLS certificate/SNI checks. Redirect following and environment proxies are disabled. DNS and checks use bounded timeouts and concurrency.

## Tests and CI

Install dependencies and run the regression suite:

```sh
python -m pip install -e '.[test]'
python -m pytest -q
```

GitHub Actions runs these pytest checks on Python 3.12 and builds the Docker image for pushes and pull requests. A workflow definition does not itself prove a successful Actions run; verify the run in GitHub after the workflow is available there.
