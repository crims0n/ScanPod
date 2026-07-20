<p align="center">
<img src="images/scanpod-logo.png" style="width: 33%;" /></p>

ScanPod is a containerized FastAPI service for distributed Nmap orchestration. Submit scan jobs, let them run async in the background, and poll for results. ScanPod will organize and track jobs, and retain results in memory.  

<p align="center">
<img src="images/demo.gif" /></p>

## Requirements

- Python 3.11+
- [nmap](https://nmap.org/) installed and available on `PATH`

## Security

**IMPORTANT!** 

At the moment, https is not supported. **DO NOT** deploy these agents on the public internet. Although the endpoint supports API authentication, without https the data is sent in cleartext and potentially interceptable.

### Input validation

`targets`, `ports`, and `arguments` are validated before a scan is created — invalid requests are rejected with `422` and never reach nmap. This prevents the raw request fields from smuggling extra nmap flags that could read or write arbitrary files or execute NSE scripts.

`arguments` is checked against an **allowlist** of safe nmap flags (scan techniques, host discovery, timing, verbosity, and OS/service detection). Flags that touch the filesystem or run scripts — `-oN`/`-oG`, `-iL`, `--script`, `-sC`, `-A`, `--datadir`, and the like — are rejected.

If you fully trust every caller and need the complete nmap surface, set `SCANPOD_ALLOW_UNSAFE_ARGS=true` to bypass the `arguments` allowlist. Target and port validation still applies. Leave this off unless you understand the risk.

## Installation

```bash
pip install -e ".[dev]"
```

## Configuration

Set environment variables with the `SCANPOD_` prefix, or create a `.env` file (see `.env.example`):

| Variable                  | Default    | Description                        |
|---------------------------|------------|------------------------------------|
| `SCANPOD_API_KEY`         | `changeme` | API key for `X-API-Key` header     |
| `SCANPOD_SCAN_TIMEOUT`    | `900`      | nmap scan timeout in seconds (server-wide default) |
| `SCANPOD_MAX_SCAN_WORKERS`| `4`        | Max concurrent background scans    |
| `SCANPOD_ALLOW_UNSAFE_ARGS`| `false`   | Bypass the nmap argument allowlist (see [Input validation](#input-validation)) |
| `SCANPOD_MAX_JOBS`        | `1000`     | Max jobs retained in memory; further submissions get `429`. `0` = unlimited |
| `SCANPOD_JOB_TTL_SECONDS` | `3600`     | Seconds a finished job is retained before eviction. `0` = keep forever |
| `SCANPOD_LOG_LEVEL`       | `INFO`     | Python log level (DEBUG, INFO, WARNING, etc.) |
| `SCANPOD_LOG_FILE`        | _(empty)_  | Path to log file; empty = stdout only |

## Running

```bash
uvicorn app.main:app --reload
```

### Docker

```bash
docker compose up -d
```

The container bundles `nmap` and runs as a non-root user. Configure via environment variables in `docker-compose.yml` or a `.env` file.

## API

All `/scans` endpoints require an `X-API-Key` header.

### Health check

```
GET /health
```

Returns `{"status": "ok"}`. No auth required.

### Create a scan

```
POST /scans
Content-Type: application/json
X-API-Key: changeme

{
  "targets": "192.168.1.0/24",
  "ports": "22,80,443",
  "arguments": "-sV",
  "timeout": 120
}
```

Returns `202` with a job ID:

```json
{
  "job_id": "abc123",
  "status": "pending",
  "created_at": "2026-02-05T12:00:00Z"
}
```

`ports`, `arguments`, and `timeout` are optional. `timeout` overrides `SCANPOD_SCAN_TIMEOUT` for that specific scan.

### Get scan status

```
GET /scans/{job_id}
X-API-Key: changeme
```

Returns `200` with full job details (including `result` once completed), or `404` if not found.

### List all scans

```
GET /scans
X-API-Key: changeme
```

Returns `200` with a summary list of all jobs (job ID and status only). Use `GET /scans/{job_id}` for full details.

### Cancel a scan

```
POST /scans/{job_id}/cancel
X-API-Key: changeme
```

Returns `200` with the updated job (status `cancelled`). Returns `404` if the job doesn't exist, or `409` if the job is already in a terminal state (`completed`, `failed`, or `cancelled`).

Cancellation is best-effort for running jobs — nmap is a blocking call and cannot be interrupted mid-scan. If a scan is in progress, the result will be discarded once nmap returns and the job will be marked `cancelled`.

### Delete a scan

```
DELETE /scans/{job_id}
X-API-Key: changeme
```

Returns `204` on success. Returns `404` if the job doesn't exist, or `409` if the job is still active (`pending` or `running`) — cancel it first.

### Purge finished scans

```
DELETE /scans
X-API-Key: changeme
```

Deletes every job in a terminal state (`completed`, `failed`, `cancelled`) in one call and returns `200` with `{"deleted": <count>}`. Active jobs (`pending`, `running`) are left untouched. Handy for reclaiming capacity after a `429`.

## curl Examples

All examples assume the service is running at `http://localhost:8000` with the default API key.

### Health check

```bash
curl http://localhost:8000/health
```

### Create a scan

```bash
curl -s -X POST http://localhost:8000/scans \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{"targets": "192.168.1.0/24", "ports": "22,80,443", "arguments": "-sV", "timeout": 120}'
```

### Get scan status / results

```bash
curl -s http://localhost:8000/scans/<job_id> \
  -H "X-API-Key: changeme"
```

### List all scans

```bash
curl -s http://localhost:8000/scans \
  -H "X-API-Key: changeme"
```

### Cancel a scan

```bash
curl -s -X POST http://localhost:8000/scans/<job_id>/cancel \
  -H "X-API-Key: changeme"
```

### Delete a scan

```bash
curl -s -X DELETE http://localhost:8000/scans/<job_id> \
  -H "X-API-Key: changeme"
```

### Purge all finished scans

```bash
curl -s -X DELETE http://localhost:8000/scans \
  -H "X-API-Key: changeme"
```

### Poll until complete, then delete

```bash
JOB_ID=$(curl -s -X POST http://localhost:8000/scans \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{"targets": "192.168.1.1"}' | jq -r .job_id)

# Poll until done
while true; do
  STATUS=$(curl -s http://localhost:8000/scans/$JOB_ID \
    -H "X-API-Key: changeme" | jq -r .status)
  echo "Status: $STATUS"
  [[ "$STATUS" == "completed" || "$STATUS" == "failed" || "$STATUS" == "cancelled" ]] && break
  sleep 5
done

# Delete the job
curl -s -X DELETE http://localhost:8000/scans/$JOB_ID \
  -H "X-API-Key: changeme"
```

## Scan Concurrency

`SCANPOD_MAX_SCAN_WORKERS` (default: `4`) controls how many scans run simultaneously. Additional submissions queue as `pending` and execute as workers free up.

**4 concurrent scans is a reasonable default**, but the practical ceiling depends on your scan profile:

- **Light scans** (small targets, few ports): 4–8 workers is fine.
- **Heavy scans** (`-sV`, large CIDRs, `-p-`): consider dropping to 2 — multiple aggressive nmap processes compete for CPU and network bandwidth and can saturate a NIC or trigger rate limiting on target networks.

A few other things to be aware of as load increases:

- **File descriptors**: each nmap subprocess opens raw sockets. Default OS limits (256 on macOS, 1024 on Linux) can become tight with wide port scans across several workers.
- **Memory**: finished job results are held in memory, but growth is bounded by two knobs. `SCANPOD_JOB_TTL_SECONDS` (default 1 hour) evicts terminal jobs a fixed time after they finish, and `SCANPOD_MAX_JOBS` (default 1000) caps total retained jobs — submissions past the cap are rejected with `429`. Set either to `0` to disable it. Eviction is lazy (swept on the next store access), so fetch results before they age out.

## Logging

ScanPod emits structured log lines to stdout by default. Key events logged include scan creation, scan completion, and failed authentication attempts.

To also write logs to a file, set `SCANPOD_LOG_FILE` to a path. The file will automatically rotate at 5 MB with 3 backups kept.

```bash
# Write logs to a file and increase verbosity
SCANPOD_LOG_LEVEL=DEBUG SCANPOD_LOG_FILE=/var/log/scanpod.log uvicorn app.main:app
```

## Architecture

The client submits a scan, gets a job ID immediately, and polls for results while nmap runs in a background thread.

| Module | Purpose |
|---|---|
| `app/main.py` | FastAPI entry point; mounts the scans router and exposes `/health` |
| `app/config.py` | Pydantic `Settings` class reading `SCANPOD_`-prefixed env vars |
| `app/auth.py` | `require_api_key()` dependency that validates the `X-API-Key` header |
| `app/models.py` | Pydantic schemas for requests, results, and job status (pending, running, completed, failed, cancelled) |
| `app/validation.py` | Validates `targets`/`ports` and enforces the nmap `arguments` allowlist |
| `app/store.py` | Thread-safe in-memory `JobStore` (dict + lock) with a job cap and TTL eviction of finished jobs |
| `app/scanner.py` | Core engine; runs blocking `python-nmap` scans in a `ThreadPoolExecutor` |
| `app/routes/scans.py` | `POST /scans`, `GET /scans/{job_id}`, `GET /scans`, `DELETE /scans` (purge finished), `POST /scans/{job_id}/cancel`, `DELETE /scans/{job_id}` endpoints |

## Testing

```bash
pytest
```

Tests mock `nmap` so no actual scanning occurs and no nmap binary is needed.
