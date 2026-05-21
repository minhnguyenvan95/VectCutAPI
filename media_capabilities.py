import json
import os
import tempfile
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

PEXELS_BASE = "https://api.pexels.com"
PIXABAY_IMAGE_VIDEO_BASE = "https://pixabay.com/api"
PIXABAY_AUDIO_BASE = "https://pixabay.com/api/audio"


class MediaProviderError(Exception):
    pass


def _load_config_keys() -> tuple[str, str]:
    pexels_env_set = "PEXELS_API_KEY" in os.environ
    pixabay_env_set = "PIXABAY_API_KEY" in os.environ
    pexels = os.getenv("PEXELS_API_KEY", "")
    pixabay = os.getenv("PIXABAY_API_KEY", "")

    try:
        from settings.local import PEXELS_API_KEY as _PEXELS_API_KEY, PIXABAY_API_KEY as _PIXABAY_API_KEY
        if not pexels_env_set:
            pexels = pexels or (_PEXELS_API_KEY or "")
        if not pixabay_env_set:
            pixabay = pixabay or (_PIXABAY_API_KEY or "")
    except Exception:
        pass

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            config = {}
            try:
                import json5
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json5.load(f)
            except Exception:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                if not pexels_env_set:
                    pexels = pexels or config.get("pexels_api_key", "")
                if not pixabay_env_set:
                    pixabay = pixabay or config.get("pixabay_api_key", "")
        except Exception:
            pass
    return pexels, pixabay


def _http_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Dict[str, Any]:
    req_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(512).decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise MediaProviderError(
            f"Search HTTP error: status={e.code}, reason={e.reason}, url={url}, response_snippet={body}"
        )
    except urllib.error.URLError as e:
        raise MediaProviderError(f"Search URL error: reason={e.reason}, url={url}")


def _download_file(url: str, output_path: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    if not output_path:
        suffix = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".bin"
        fd, output_path = tempfile.mkstemp(prefix="vectcut_media_", suffix=suffix)
        os.close(fd)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pexels.com/",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(output_path, "wb") as f:
            f.write(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(512).decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise MediaProviderError(
            f"Download HTTP error: status={e.code}, reason={e.reason}, url={url}, output_path={output_path}, response_snippet={body}"
        )
    except urllib.error.URLError as e:
        raise MediaProviderError(f"Download URL error: reason={e.reason}, url={url}, output_path={output_path}")

    return {"local_path": output_path, "source_url": url}


def _is_pexels_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate" in text or "limit" in text


def _normalize_pixabay_per_page(per_page: int) -> int:
    if per_page < 3:
        return 3
    if per_page > 200:
        return 200
    return per_page


def _ensure_key(key: str, name: str) -> None:
    if not key:
        raise MediaProviderError(f"Missing {name}. Configure in config.json")


def search_images(
    query: str,
    page: int = 1,
    per_page: int = 15,
    orientation: Optional[str] = None,
    size: Optional[str] = None,
    color: Optional[str] = None,
    locale: Optional[str] = None,
    category: Optional[str] = None,
    lang: Optional[str] = None,
    image_type: Optional[str] = None,
    colors: Optional[str] = None,
    editors_choice: Optional[bool] = None,
    safesearch: Optional[bool] = None,
    order: Optional[str] = None,
    min_width: Optional[int] = None,
    min_height: Optional[int] = None,
) -> Dict[str, Any]:
    pexels_key, pixabay_key = _load_config_keys()
    _ensure_key(pexels_key or pixabay_key, "pexels_api_key or pixabay_api_key")

    if pexels_key:
        try:
            pexels_params = {"query": query, "page": page, "per_page": per_page}
            if orientation:
                pexels_params["orientation"] = orientation
            if size:
                pexels_params["size"] = size
            if color:
                pexels_params["color"] = color
            if locale:
                pexels_params["locale"] = locale
            qs = urllib.parse.urlencode(pexels_params)
            data = _http_json(f"{PEXELS_BASE}/v1/search?{qs}", headers={"Authorization": pexels_key})
            return {"provider": "pexels", "data": data}
        except Exception as exc:
            if not pixabay_key or not _is_pexels_limit_error(exc):
                raise

    _ensure_key(pixabay_key, "pixabay_api_key")
    pixabay_params = {
        "key": pixabay_key,
        "q": query,
        "page": page,
        "per_page": _normalize_pixabay_per_page(per_page),
    }
    if category:
        pixabay_params["category"] = category
    if lang:
        pixabay_params["lang"] = lang
    if image_type:
        pixabay_params["image_type"] = image_type
    if orientation:
        pixabay_params["orientation"] = orientation
    if colors:
        pixabay_params["colors"] = colors
    if editors_choice is not None:
        pixabay_params["editors_choice"] = str(editors_choice).lower()
    if safesearch is not None:
        pixabay_params["safesearch"] = str(safesearch).lower()
    if order:
        pixabay_params["order"] = order
    if min_width is not None:
        pixabay_params["min_width"] = min_width
    if min_height is not None:
        pixabay_params["min_height"] = min_height
    qs = urllib.parse.urlencode(pixabay_params)
    data = _http_json(f"{PIXABAY_IMAGE_VIDEO_BASE}/?{qs}")
    return {"provider": "pixabay", "data": data}


def search_videos(
    query: str,
    page: int = 1,
    per_page: int = 15,
    orientation: Optional[str] = None,
    size: Optional[str] = None,
    locale: Optional[str] = None,
    min_width: Optional[int] = None,
    min_height: Optional[int] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None,
    category: Optional[str] = None,
    lang: Optional[str] = None,
    video_type: Optional[str] = None,
    editors_choice: Optional[bool] = None,
    safesearch: Optional[bool] = None,
    order: Optional[str] = None,
) -> Dict[str, Any]:
    pexels_key, pixabay_key = _load_config_keys()
    _ensure_key(pexels_key or pixabay_key, "pexels_api_key or pixabay_api_key")

    if pexels_key:
        try:
            pexels_params = {"query": query, "page": page, "per_page": per_page}
            if orientation:
                pexels_params["orientation"] = orientation
            if size:
                pexels_params["size"] = size
            if locale:
                pexels_params["locale"] = locale
            if min_width is not None:
                pexels_params["min_width"] = min_width
            if min_height is not None:
                pexels_params["min_height"] = min_height
            if min_duration is not None:
                pexels_params["min_duration"] = min_duration
            if max_duration is not None:
                pexels_params["max_duration"] = max_duration
            qs = urllib.parse.urlencode(pexels_params)
            data = _http_json(f"{PEXELS_BASE}/videos/search?{qs}", headers={"Authorization": pexels_key})
            return {"provider": "pexels", "data": data}
        except Exception as exc:
            if not pixabay_key or not _is_pexels_limit_error(exc):
                raise

    _ensure_key(pixabay_key, "pixabay_api_key")
    pixabay_params = {
        "key": pixabay_key,
        "q": query,
        "page": page,
        "per_page": _normalize_pixabay_per_page(per_page),
    }
    if category:
        pixabay_params["category"] = category
    if lang:
        pixabay_params["lang"] = lang
    if video_type:
        pixabay_params["video_type"] = video_type
    if min_width is not None:
        pixabay_params["min_width"] = min_width
    if min_height is not None:
        pixabay_params["min_height"] = min_height
    if editors_choice is not None:
        pixabay_params["editors_choice"] = str(editors_choice).lower()
    if safesearch is not None:
        pixabay_params["safesearch"] = str(safesearch).lower()
    if order:
        pixabay_params["order"] = order
    qs = urllib.parse.urlencode(pixabay_params)
    data = _http_json(f"{PIXABAY_IMAGE_VIDEO_BASE}/videos/?{qs}")
    return {"provider": "pixabay", "data": data}


def search_audio(query: str, page: int = 1, per_page: int = 15) -> Dict[str, Any]:
    _, pixabay_key = _load_config_keys()
    _ensure_key(pixabay_key, "pixabay_api_key")
    qs = urllib.parse.urlencode({
        "key": pixabay_key,
        "q": query,
        "page": page,
        "per_page": _normalize_pixabay_per_page(per_page),
    })
    data = _http_json(f"{PIXABAY_AUDIO_BASE}/?{qs}")
    return {"provider": "pixabay", "data": data}


def get_image_by_id(media_id: int) -> Dict[str, Any]:
    pexels_key, pixabay_key = _load_config_keys()
    if pexels_key:
        try:
            data = _http_json(f"{PEXELS_BASE}/v1/photos/{media_id}", headers={"Authorization": pexels_key})
            return {"provider": "pexels", "data": data}
        except Exception as exc:
            if not pixabay_key or not _is_pexels_limit_error(exc):
                raise

    _ensure_key(pixabay_key, "pixabay_api_key")
    qs = urllib.parse.urlencode({"key": pixabay_key, "id": media_id})
    data = _http_json(f"{PIXABAY_IMAGE_VIDEO_BASE}/?{qs}")
    return {"provider": "pixabay", "data": data}


def get_video_by_id(media_id: int) -> Dict[str, Any]:
    pexels_key, pixabay_key = _load_config_keys()
    if pexels_key:
        try:
            data = _http_json(f"{PEXELS_BASE}/videos/videos/{media_id}", headers={"Authorization": pexels_key})
            return {"provider": "pexels", "data": data}
        except Exception as exc:
            if not pixabay_key or not _is_pexels_limit_error(exc):
                raise

    _ensure_key(pixabay_key, "pixabay_api_key")
    qs = urllib.parse.urlencode({"key": pixabay_key, "id": media_id})
    data = _http_json(f"{PIXABAY_IMAGE_VIDEO_BASE}/videos/?{qs}")
    return {"provider": "pixabay", "data": data}


def get_audio_by_id(media_id: int) -> Dict[str, Any]:
    _, pixabay_key = _load_config_keys()
    _ensure_key(pixabay_key, "pixabay_api_key")
    qs = urllib.parse.urlencode({"key": pixabay_key, "id": media_id})
    data = _http_json(f"{PIXABAY_AUDIO_BASE}/?{qs}")
    return {"provider": "pixabay", "data": data}


def download_image(url: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    return _download_file(url, output_path=output_path)


def download_video(url: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    return _download_file(url, output_path=output_path)


def download_audio(url: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    return {
        "manual_download_required": True,
        "message": "Direct audio download is disabled. Open this URL in browser to download audio manually.",
        "browser_url": url,
        "suggested_output_path": output_path or ""
    }
