# Site Monitor

Automated site monitoring via GitHub Actions. Visits URLs from `urls.txt`, captures full-page screenshots, uploads them to a private Hugging Face dataset, and records date/status to `status_log.json` in this repo.

## How it works

1. The workflow runs **every 2 hours** (or manually via **Run workflow** → `workflow_dispatch`).
2. Reads URLs from `urls.txt` (one per line, `#` lines ignored).
3. Uses Playwright headless Chrome to visit each URL and take a full-page screenshot.
4. Screenshot is saved as `{domain}_{YYYY-MM-DD}.png`.
5. If the dataset does not exist, a **new private dataset** is created automatically (`HF_USERNAME/HF_DATASET`).
6. Screenshot is uploaded to the dataset.
7. Deletes dataset files **older than 7 days** (configurable via `CLEANUP_DAYS`).
8. Updates `status_log.json` with the run timestamp and each URL's status, then commits it to the repo (using the configured GH identity).
9. Squashes git history into a single commit and cleans up old workflow runs to keep the repo small.

## Setup

### 1. Configure GitHub Secrets

In **Settings → Secrets and variables → Actions**, add:

| Secret | Description | Required | Example |
|--------|-------------|----------|---------|
| `HF_TOKEN` | Hugging Face access token (write permission) | ✅ | `hf_xxxx` |
| `HF_USERNAME` | HF username/namespace for the dataset | ✅ | `YOUR_HF_USERNAME` |
| `HF_DATASET` | HF dataset name (without username) | ✅ | `siteMonitor` |
| `GH_USERNAME` | Git identity username for commits | ❌ (default `github-actions[bot]`) | `YOUR_GITHUB_USERNAME` |
| `GH_EMAIL` | Git identity email for commits | ❌ (default bot email) | `your@email.com` |
| `CLEANUP_DAYS` | Delete dataset files older than this many days | ❌ (default `7`) | `7` |

### 2. Add `urls.txt`

List the URLs to monitor, one per line. Lines starting with `#` are ignored.

## Status Log Format

`status_log.json`:

```json
{
  "runtime": "2026-09-03T01:54:56Z",
  "status": "ok",
  "http_status": 200,
  "uploaded": true
}
```

## Local Run

```bash
pip install -r requirements.txt
python -m playwright install chromium
export HF_TOKEN=...
export HF_USERNAME=YOUR_HF_USERNAME
export HF_DATASET=siteMonitor
python monitor.py
```