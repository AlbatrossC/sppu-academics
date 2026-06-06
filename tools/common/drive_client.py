"""Google Drive API v3 client for public folders using an API key."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Iterator

import requests
from dotenv import load_dotenv

from common.utils import PROJECT_ROOT


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
PDF_MIME_TYPE = "application/pdf"


class DriveClientError(RuntimeError):
    """Raised for unrecoverable Google Drive API failures."""


class GoogleDriveClient:
    """Small Google Drive API v3 client with retry and rate-limit handling."""

    base_url = "https://www.googleapis.com/drive/v3"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
        max_retries: int = 5,
        backoff_factor: float = 1.5,
        logger: logging.Logger | None = None,
    ) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "").strip()
        if not self.api_key:
            raise DriveClientError("GOOGLE_API_KEY is missing. Add it to .env.")

        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Perform a Drive API request with exponential backoff."""
        params = dict(kwargs.pop("params", {}) or {})
        params["key"] = self.api_key
        url = f"{self.base_url}{path}"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(method, url, params=params, timeout=self.timeout, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    if response.status_code >= 400:
                        raise DriveClientError(self._format_api_error(response))
                    return response

                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else self.backoff_factor * (2**attempt)
                self.logger.warning("Drive API throttled or unavailable (%s); retrying in %.1fs", response.status_code, delay)
                time.sleep(delay)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                delay = self.backoff_factor * (2**attempt)
                self.logger.warning("Drive API request failed: %s; retrying in %.1fs", exc, delay)
                time.sleep(delay)

        if last_error is not None:
            raise DriveClientError(f"Drive API request failed after retries: {last_error}") from last_error
        raise DriveClientError("Drive API request failed after retries.")

    @staticmethod
    def _format_api_error(response: requests.Response) -> str:
        try:
            payload = response.json()
            message = payload.get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        lowered = message.lower()
        if "automated queries" in lowered or "<title>sorry" in lowered or "we're sorry" in lowered:
            return (
                f"Drive API error {response.status_code}: Google anti-automation/rate limit block. "
                "Stop and retry later, or retry with fewer workers and a larger delay."
            )
        return f"Drive API error {response.status_code}: {message}"

    def list_children(self, parent_id: str, mime_type: str | None = None) -> list[dict[str, Any]]:
        """List non-trashed children for a Drive folder."""
        query_parts = [f"'{parent_id}' in parents", "trashed = false"]
        if mime_type:
            query_parts.append(f"mimeType = '{mime_type}'")

        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "q": " and ".join(query_parts),
                "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                "pageSize": 1000,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            response = self._request("GET", "/files", params=params)
            payload = response.json()
            items.extend(payload.get("files", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                return items

    def list_folders(self, parent_id: str) -> list[dict[str, Any]]:
        """List child folders for a Drive folder."""
        return self.list_children(parent_id, FOLDER_MIME_TYPE)

    def list_pdfs(self, parent_id: str) -> list[dict[str, Any]]:
        """List PDFs directly inside a Drive folder."""
        files = self.list_children(parent_id, PDF_MIME_TYPE)
        return sorted(files, key=lambda item: item.get("name", "").lower())

    def walk_folders(self, root_folder_id: str) -> Iterator[tuple[str, str, str]]:
        """Yield all descendant folders as (path, folder_id, parent_id)."""
        stack: list[tuple[str, str]] = [("", root_folder_id)]
        while stack:
            current_path, parent_id = stack.pop()
            label = current_path or "<root>"
            self.logger.info("Scanning folder: %s (%s)", label, parent_id)
            folders = sorted(self.list_folders(parent_id), key=lambda item: item.get("name", "").lower(), reverse=True)
            self.logger.info("Found %d child folders in %s", len(folders), label)
            for folder in folders:
                name = folder["name"]
                folder_path = f"{current_path}/{name}" if current_path else name
                yield folder_path, folder["id"], parent_id
                stack.append((folder_path, folder["id"]))

    def download_file(self, file_id: str, destination: Path) -> None:
        """Download a Drive file by ID to destination."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._request("GET", f"/files/{file_id}", params={"alt": "media"}, stream=True)
        temp_path = destination.with_suffix(destination.suffix + ".part")
        with temp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        temp_path.replace(destination)
