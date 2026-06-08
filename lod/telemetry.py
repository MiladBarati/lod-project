import datetime
import json
import logging
import os
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    import asyncio
except ImportError:
    asyncio = None


logger = logging.getLogger("lod.telemetry")


def resolve_telemetry_config(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> tuple:
    """Resolves telemetry configuration, falling back to environment variables if parameters are None."""
    if endpoint is None:
        endpoint = os.environ.get("LOD_TELEMETRY_ENDPOINT")
    if api_key is None:
        api_key = os.environ.get("LOD_TELEMETRY_API_KEY")
    if enabled is None:
        env_enabled = os.environ.get("LOD_TELEMETRY_ENABLED")
        if env_enabled is not None:
            enabled = env_enabled.lower() in ("true", "1", "yes")
        else:
            enabled = True
    return endpoint, api_key, enabled


def sanitize_url(url: str) -> str:
    """Redacts query parameter values in the URL to preserve user privacy."""
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.query:
            return url
        query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        sanitized_params = []
        for name, _ in query_params:
            sanitized_params.append((name, "[REDACTED]"))
        new_query = urllib.parse.urlencode(sanitized_params)
        parts = list(parsed)
        parts[4] = new_query
        return urllib.parse.urlunparse(parts)
    except Exception:
        return url


def get_iso_timestamp() -> str:
    """Returns the current UTC ISO-8601 timestamp."""
    return datetime.datetime.utcnow().isoformat() + "Z"


class SyncTelemetryReporter:
    """Synchronous daemon thread-based telemetry reporter for requests and sync httpx."""

    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None, enabled: Optional[bool] = None):
        endpoint, api_key, enabled = resolve_telemetry_config(endpoint, api_key, enabled)
        self.endpoint = endpoint
        self.api_key = api_key
        self.enabled = enabled and bool(endpoint)
        self.queue = queue.Queue(maxsize=1000)
        self._thread = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def start(self):
        with self._lock:
            if self._thread is None and self.enabled:
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()

    def stop(self):
        with self._lock:
            if self._thread is not None:
                self._stop_event.set()
                try:
                    self.queue.put_nowait(None)
                except queue.Full:
                    pass
                self._thread.join(timeout=1.0)
                self._thread = None

    def report_validation_error(self, method: str, url: str, errors: List[Dict[str, Any]]):
        if not self.enabled:
            return

        # Start worker thread lazily
        if self._thread is None:
            self.start()

        event = {
            "method": method.upper(),
            "url": sanitize_url(url),
            "errors": errors,
            "timestamp": get_iso_timestamp(),
        }
        try:
            self.queue.put(event, timeout=0.1)
        except queue.Full:
            logger.warning("LOD telemetry queue is full, dropping event.")

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                event = self.queue.get(timeout=0.5)
                if event is None:
                    self.queue.task_done()
                    break

                self._send_event(event)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.warning(f"LOD telemetry worker encountered unexpected error: {e}")

    def _send_event(self, event: Dict[str, Any]):
        if not self.endpoint:
            return

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(event).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=2.0) as response:
                response.read()
        except urllib.error.URLError as e:
            logger.warning(f"LOD telemetry failed to send event to {self.endpoint}: {e}")
        except Exception as e:
            logger.warning(f"LOD telemetry sending error: {e}")


class AsyncTelemetryReporter:
    """Asynchronous reporter using asyncio.Queue and background task for async httpx."""

    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None, enabled: Optional[bool] = None):
        endpoint, api_key, enabled = resolve_telemetry_config(endpoint, api_key, enabled)
        self.endpoint = endpoint
        self.api_key = api_key
        self.enabled = enabled and bool(endpoint)
        self.queue = asyncio.Queue(maxsize=1000) if asyncio else None
        self._task = None
        self._client = None
        self._lock = asyncio.Lock() if asyncio else None

    async def start(self):
        if not asyncio or not self.enabled:
            return
        async with self._lock:
            if self._task is None:
                self._client = httpx.AsyncClient(timeout=2.0) if httpx else None
                self._task = asyncio.create_task(self._worker())

    async def stop(self):
        if not asyncio:
            return
        async with self._lock:
            if self._task is not None:
                await self.queue.put(None)
                try:
                    await asyncio.wait_for(self._task, timeout=1.0)
                except asyncio.TimeoutError:
                    if self._task:
                        self._task.cancel()
                self._task = None
            if self._client:
                await self._client.aclose()
                self._client = None

    async def report_validation_error(self, method: str, url: str, errors: List[Dict[str, Any]]):
        if not self.enabled or not asyncio:
            return

        if self._task is None:
            await self.start()

        event = {
            "method": method.upper(),
            "url": sanitize_url(url),
            "errors": errors,
            "timestamp": get_iso_timestamp(),
        }
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("LOD async telemetry queue is full, dropping event.")

    async def _worker(self):
        while True:
            try:
                event = await self.queue.get()
                if event is None:
                    self.queue.task_done()
                    break

                await self._send_event(event)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"LOD async telemetry worker encountered unexpected error: {e}")

    async def _send_event(self, event: Dict[str, Any]):
        if not self.endpoint or not self._client:
            return

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = await self._client.post(
                self.endpoint,
                json=event,
                headers=headers
            )
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"LOD async telemetry failed to send event: {e}")
