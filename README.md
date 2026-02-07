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

## Installation

```bash
pip install -e ".[dev]"
```

## Configuration

Set environment variables with the `SCANPOD_` prefix, or create a `.env` file (see `.env.example`):

| Variable                  | Default    | Description                        |
|---------------------------|------------|------------------------------------|
| `SCANPOD_API_KEY`         | `changeme` | API key for `X-API-Key` header     |
| `SCANPOD_SCAN_TIMEOUT`    | `300`      | nmap scan timeout in seconds       |
| `SCANPOD_MAX_SCAN_WORKERS`| `4`        | Max concurrent background scans    |
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
  "arguments": "-sV"
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

`ports` and `arguments` are optional.

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
| `app/models.py` | Pydantic schemas for requests, results, and job status (pending, running, completed, failed) |
| `app/store.py` | Thread-safe in-memory `JobStore` backed by a dict and threading lock |
| `app/scanner.py` | Core engine; runs blocking `python-nmap` scans in a `ThreadPoolExecutor` |
| `app/routes/scans.py` | `POST /scans`, `GET /scans/{job_id}`, and `GET /scans` endpoints |

## Testing

```bash
pytest
```

Tests mock `nmap` so no actual scanning occurs and no nmap binary is needed.
