#!/usr/bin/env python3
"""Site Monitor - visits URLs, captures screenshots, uploads to a private HF dataset,
and records date/status to status_log.json in the repo."""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from huggingface_hub import HfApi, RepoFile, upload_file
from playwright.sync_api import sync_playwright

URLS_FILE = "urls.txt"
STATUS_FILE = "status_log.json"
SHOT_DIR = "screenshots"


def read_urls(path: str) -> list:
    if not os.path.exists(path):
        print(f"[!] urls file not found: {path}")
        return []
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def domain_from_url(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url)
    host = match.group(1) if match else url.replace("://", "_")
    return re.sub(r"[^a-zA-Z0-9_.]", "_", host)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dataset(api: HfApi, repo_id: str) -> None:
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
        print(f"[ok] dataset '{repo_id}' already exists")
    except Exception:
        try:
            api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)
            print(f"[ok] created private dataset '{repo_id}'")
        except Exception as e:
            print(f"[err] could not create dataset '{repo_id}': {e}")
            raise


def cleanup_old_files(api: HfApi, repo_id: str, days: int) -> None:
    if days <= 0:
        return
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        to_delete = []
        for item in api.list_repo_tree(repo_id=repo_id, repo_type="dataset", recursive=True):
            if isinstance(item, RepoFile):
                commit = getattr(item, "last_commit", None)
                created = getattr(commit, "created_at", None) if commit else None
                if created and created.replace(tzinfo=timezone.utc) < cutoff:
                    to_delete.append(item.path)
        if to_delete:
            api.delete_files(
                files=to_delete,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"Cleanup: remove files older than {days} days",
            )
            print(f"[ok] cleaned {len(to_delete)} file(s) older than {days} days")
        else:
            print(f"[i] no files older than {days} days")
    except Exception as e:
        print(f"[err] cleanup failed: {e}")


def upload_to_hf(repo_id: str, token: str, file_path: str, filename: str) -> bool:
    try:
        upload_file(
            path_or_fileobj=file_path,
            path_in_repo=filename,
            repo_id=repo_id,
            token=token,
            repo_type="dataset",
        )
        print(f"    [ok] uploaded {filename} -> {repo_id}")
        return True
    except Exception as e:
        print(f"    [err] upload failed: {e}")
        return False


def main() -> int:
    hf_token = os.getenv("HF_TOKEN", "")
    hf_username = os.getenv("HF_USERNAME", "")
    hf_dataset = os.getenv("HF_DATASET", "")
    cleanup_days = int(os.getenv("CLEANUP_DAYS") or "7")

    if not hf_token:
        print("[err] HF_TOKEN env var is required")
        return 1

    if hf_dataset and "/" not in hf_dataset and hf_username:
        hf_dataset = f"{hf_username}/{hf_dataset}"
        print(f"[i] dataset resolved to '{hf_dataset}'")

    urls = read_urls(URLS_FILE)
    if not urls:
        print("[!] no urls found, nothing to do")
        return 0

    os.makedirs(SHOT_DIR, exist_ok=True)
    api = HfApi(token=hf_token)
    if hf_dataset:
        ensure_dataset(api, hf_dataset)
    timestamp = now_iso()
    run = {"runtime": timestamp, "status": "ok", "http_status": 200, "uploaded": True}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for url in urls:
            domain = domain_from_url(url)
            date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            filename = f"{domain}_{date_part}.png"
            file_path = os.path.join(SHOT_DIR, filename)

            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                resp = page.goto(url, timeout=30000, wait_until="load")
                status = resp.status if resp else 0
                page.wait_for_timeout(3000)
                page.screenshot(path=file_path, full_page=True)
                page.close()

                print(f"[ok] {url} -> {filename} (HTTP {status})")

                if status != 200:
                    run["http_status"] = status

                if hf_dataset and os.path.exists(file_path):
                    hf_ok = upload_to_hf(hf_dataset, hf_token, file_path, filename)
                    if not hf_ok:
                        run["uploaded"] = False
            except Exception as e:
                run["status"] = "error"
                run["uploaded"] = False
                print(f"[err] {url}: {e}")

        browser.close()

    if hf_dataset:
        cleanup_old_files(api, hf_dataset, cleanup_days)

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2)

    print(f"\n[done] {len(urls)} urls checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
