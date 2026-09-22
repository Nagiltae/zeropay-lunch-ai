"""Playwright 없이 KOMSCO 원천과 provider manifest를 읽는 입력 모듈."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from app.naver.place_resolver import RestaurantReference


def load_local_env(root: Path) -> None:
    """Playwright resolver를 import하지 않고 로컬 환경값만 읽는다."""
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_provider_manifest(path: Path) -> tuple[RestaurantReference, ...]:
    """Read a stable manifest; no database or network access is performed."""
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(
            line for line in stream if line.strip() and not line.lstrip().startswith("#")
        ))
    required = {"external_merchant_id", "komsco_name", "komsco_address"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"provider manifest requires columns: {sorted(required)}")
    identities = [row.get("external_merchant_id", "").strip() for row in rows]
    if any(not identity for identity in identities) or len(identities) != len(set(identities)):
        raise ValueError(
            f"provider manifest contains missing or duplicate external identities: {path}"
        )
    references = []
    for row in rows:
        name = row.get("komsco_name", "").strip()
        address = row.get("komsco_address", "").strip()
        if not name or not address:
            raise ValueError(f"provider manifest contains empty source fields: {path}")
        references.append(RestaurantReference(
            restaurant_id=int(row.get("restaurant_id") or 0),
            komsco_name=name,
            komsco_address=address,
            komsco_latitude=_float(row.get("komsco_lat") or row.get("latitude")),
            komsco_longitude=_float(row.get("komsco_lon") or row.get("longitude")),
            legal_dong=row.get("legal_dong_name", "논현동"),
            external_merchant_id=identities[len(references)],
            processing_reason=row.get("processing_reason", ""),
        ))
    return tuple(references)
