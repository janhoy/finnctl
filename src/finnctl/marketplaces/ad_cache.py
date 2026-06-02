"""
Local ad cache for finnctl.

Storage layout:
  ~/.finnctl/cache/<folder>/
    meta.json   – { finn_id, name, title, marketplace, cached_at }
    ad.json     – full edit-form payload from /recommerce/create/<id>
    images/
      0.jpg, 1.jpg, …

<folder> is the finn_id, or a user-supplied --name.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx


CACHE_DIR = Path.home() / ".finnctl" / "cache"
IMAGE_CDN = "https://images.finncdn.no/dynamic/1280w/"


@dataclass
class CachedAd:
    folder: Path
    finn_id: str
    name: str       # folder name (may equal finn_id)
    title: str
    marketplace: str
    cached_at: str  # ISO-8601


class AdCache:

    @staticmethod
    def resolve(id_or_name: str) -> Path:
        """Return the cache folder path for a given finn_id or name."""
        return CACHE_DIR / id_or_name

    @staticmethod
    def find(id_or_name: str) -> Path:
        """
        Return the cache folder, searching by both folder name and finn_id
        stored in meta.json. Raises FileNotFoundError if not found.
        """
        direct = CACHE_DIR / id_or_name
        if (direct / "meta.json").exists():
            return direct

        # Search by finn_id in all meta files
        if CACHE_DIR.exists():
            for meta_path in CACHE_DIR.glob("*/meta.json"):
                try:
                    meta = json.loads(meta_path.read_text())
                    if str(meta.get("finn_id")) == str(id_or_name):
                        return meta_path.parent
                except Exception:
                    pass

        raise FileNotFoundError(f"No cached ad found for {id_or_name!r}")

    @staticmethod
    def list() -> list[CachedAd]:
        """List all locally cached ads, sorted by cached_at descending."""
        if not CACHE_DIR.exists():
            return []
        ads = []
        for meta_path in sorted(CACHE_DIR.glob("*/meta.json")):
            try:
                meta = json.loads(meta_path.read_text())
                ads.append(CachedAd(
                    folder=meta_path.parent,
                    finn_id=str(meta.get("finn_id", "")),
                    name=meta.get("name", meta_path.parent.name),
                    title=meta.get("title", ""),
                    marketplace=meta.get("marketplace", ""),
                    cached_at=meta.get("cached_at", ""),
                ))
            except Exception:
                continue
        return sorted(ads, key=lambda a: a.cached_at, reverse=True)

    @staticmethod
    def load_ad(id_or_name: str) -> dict:
        """Load the ad.json payload. Raises FileNotFoundError if not cached."""
        folder = AdCache.find(id_or_name)
        ad_path = folder / "ad.json"
        if not ad_path.exists():
            raise FileNotFoundError(f"ad.json missing in {folder}")
        return json.loads(ad_path.read_text())

    @staticmethod
    def save(
        finn_id: str,
        ad_payload: dict,
        image_uris: list[str],
        *,
        name: str | None = None,
        marketplace: str = "torget",
    ) -> Path:
        """
        Save the ad payload and download images to the cache folder.
        Returns the folder path.
        """
        folder_name = name or finn_id
        folder = CACHE_DIR / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        images_dir = folder / "images"
        images_dir.mkdir(exist_ok=True)

        title = ad_payload.get("data", {}).get("title", "")

        # Write ad.json
        (folder / "ad.json").write_text(
            json.dumps(ad_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Download images
        _download_images(image_uris, images_dir)

        # Write meta.json
        meta = {
            "finn_id": finn_id,
            "name": folder_name,
            "title": title,
            "marketplace": marketplace,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "image_count": len(image_uris),
        }
        (folder / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return folder

    @staticmethod
    def delete(id_or_name: str) -> Path:
        """Delete the cache folder. Returns the deleted path."""
        folder = AdCache.find(id_or_name)
        shutil.rmtree(folder)
        return folder


def _download_images(uris: list[str], dest: Path) -> None:
    """Download images from finn CDN to dest/ as 0.jpg, 1.jpg, …"""
    with httpx.Client(timeout=30.0) as client:
        for i, uri in enumerate(uris):
            url = IMAGE_CDN + uri if not uri.startswith("http") else uri
            try:
                r = client.get(url)
                r.raise_for_status()
                suffix = _image_suffix(r.headers.get("content-type", ""))
                (dest / f"{i}{suffix}").write_bytes(r.content)
            except Exception:
                pass  # skip failed images silently


def _image_suffix(content_type: str) -> str:
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"