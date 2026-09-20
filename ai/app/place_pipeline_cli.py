"""Small, resumable KOMSCO -> PCMap -> public detail pipeline.

The default is CSV-only.  Database writes require ``--write-db`` explicitly.
"""

# CLI orchestration keeps progress/report expressions together for readability.
# ruff: noqa: E501, E701, E702

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.place_dom_detail_crawler import PlaceDomDetailCrawler
from app.place_request_limiter import NavigationRateLimiter
from app.place_detail_persistence import PlaceDetailPersistence
from app.place_resolver import (
    PlaceCandidate,
    Resolution,
    ResolutionStatus,
    nearest_station,
    query_for,
    station_query,
)
from app.place_resolver_cli import (
    load_komsco_population,
    load_local_env,
    load_stations,
    load_verified_checkpoint,
    preflight,
    run_one,
    save_verified_checkpoint,
    _existing_place_mapping,
    write_resolved_to_db,
)
from app.qwen_candidate_matcher import OllamaClient, QwenCandidateMatcher

FIELDS = [
    "restaurant_id", "komsco_name", "komsco_address", "previous_naver_status",
    "naver_matched_external_name", "naver_matched_address", "naver_matched_road_address",
    "query", "place_id", "place_url", "resolve_status", "detail_status",
    "matcher_source", "qwen_used", "qwen_confidence", "naver_db_fallback_available",
    "qwen_ranking", "resolved_rank", "detail_validation_attempts",
    "validation_attempts_json",
    "detail_access_method", "http_result", "playwright_result",
    "menu_count", "parsed_menu_count", "menu_complete", "menu_fallback_used",
    "home_status", "hours_status", "menu_status", "review_status",
    "review_requested", "review_count", "review_keyword_count",
    "review_menu_mention_count", "review_theme_count", "representative_review_count",
    "detail_warnings", "result", "reason",
    "persistence_status", "persistence_error",
    "elapsed_ms",
]


def is_blocked_error(error: BaseException) -> bool:
    return str(error).startswith("BLOCKED:")


def is_fatal_persistence_error(error: BaseException) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in ("can't connect", "cannot connect", "connection refused", "timed out", "docker", "credential")
    )


def run_until_blocked(items, handler):
    """Run items in order and never invoke a later handler after BLOCKED."""
    results = []
    for item in items:
        try:
            results.append(handler(item))
        except RuntimeError as error:
            if is_blocked_error(error):
                return results, True
            raise
    return results, False


def checkpoint_result(reference, checkpoint_row):
    candidate = PlaceCandidate(
        checkpoint_row.get("resolved_name", ""),
        checkpoint_row.get("resolved_address", ""),
        "", f"https://pcmap.place.naver.com/restaurant/{checkpoint_row['place_id']}/home",
        checkpoint_row["place_id"],
    )
    return type("CheckpointResult", (), {
        "reference": reference, "query": "CHECKPOINT", "place_id": checkpoint_row["place_id"],
        "candidate": candidate, "resolution": Resolution(
            reference, "CHECKPOINT", candidate, ResolutionStatus.RESOLVED,
            "CHECKPOINT", "CHECKPOINT", "CHECKPOINT", ()
        ), "matcher_source": "VERIFIED_CHECKPOINT", "qwen_used": False,
        "qwen_confidence": "", "selected_index": 0, "detail": None,
        "qwen_candidate_indices": (0,), "detail_validation_attempts": 0,
    })()


def select_pipeline_references(references, *, restaurant_id=None, limit: int | None = None):
    """Apply explicit id filtering and a hard batch limit before processing."""
    ids = None if restaurant_id is None else set(restaurant_id if isinstance(restaurant_id, list) else [restaurant_id])
    selected = [item for item in references if ids is None or item.restaurant_id in ids]
    return selected[:limit] if limit is not None else selected


def load_batch_manifest(path: Path) -> list[int]:
    """Read a fixed restaurant-id manifest (whitespace or one id per line)."""
    values = [int(value) for value in path.read_text(encoding="utf-8").split() if value.isdigit()]
    if len(values) != len(set(values)):
        raise RuntimeError(f"manifest contains duplicate restaurant_id: {path}")
    return values


TERMINAL_LEDGER_STATES = {"RESOLVED", "AMBIGUOUS", "NOT_FOUND", "PLACE_ID_CONFLICT"}


class ResumeLedger:
    """Atomic terminal-state ledger independent from the audit CSV."""

    FIELDS = ("restaurant_id", "status", "place_id", "updated_at", "reason")

    def __init__(self, path: Path, resume: bool):
        self.path = path
        self.rows: dict[int, dict[str, str]] = {}
        if resume and path.exists() and path.stat().st_size:
            with path.open(newline="", encoding="utf-8") as stream:
                for row in csv.DictReader(stream):
                    if row.get("restaurant_id"):
                        self.rows[int(row["restaurant_id"])] = row

    def completed_ids(self, *, retry_failed: bool = False, force_resolve: bool = False) -> set[int]:
        if force_resolve:
            return set()
        if retry_failed:
            return {rid for rid, row in self.rows.items() if row.get("status") in TERMINAL_LEDGER_STATES}
        return {rid for rid, row in self.rows.items() if row.get("status") in TERMINAL_LEDGER_STATES}

    def record(self, restaurant_id: int, status: str, *, place_id: str = "", reason: str = "") -> None:
        self.rows[restaurant_id] = {
            "restaurant_id": str(restaurant_id),
            "status": status,
            "place_id": place_id,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerows(self.rows.values())
            stream.flush(); os.fsync(stream.fileno())
        temporary.replace(self.path)


class PipelineWriter:
    def __init__(self, path: Path, resume: bool, retry_failed: bool = False):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        retained: list[dict[str, str]] = []
        if resume and retry_failed and path.exists() and path.stat().st_size:
            with path.open(newline="", encoding="utf-8") as source:
                retained = [
                    row for row in csv.DictReader(source)
                    if row.get("detail_status") not in {"FAILED", "PARTIAL"}
                ]
            resume = False
        self.stream = path.open("a" if resume else "w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.stream, fieldnames=FIELDS)
        if not resume or path.stat().st_size == 0:
            self.writer.writeheader()
            for row in retained:
                self.writer.writerow(row)
            self.flush()

    def flush(self):
        self.stream.flush(); os.fsync(self.stream.fileno())

    def completed(self, retry_failed: bool = False) -> set[int]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return set()
        with self.path.open(newline="", encoding="utf-8") as stream:
            completed = set()
            for row in csv.DictReader(stream):
                if not row.get("restaurant_id"):
                    continue
                detail_status = row.get("detail_status", "")
                retryable = (
                    detail_status in {"FAILED", "PARTIAL"}
                    or row.get("resolve_status") == "ERROR"
                    or row.get("persistence_status") == "ERROR"
                )
                if retry_failed and retryable:
                    continue
                completed.add(int(row["restaurant_id"]))
            return completed

    def append(self, row: dict[str, object]):
        self.writer.writerow(row); self.flush()

    def close(self):
        self.stream.close()


def _row(result, previous: str, detail_result, elapsed: int, reason: str = "", naver_reference=None, *, persistence_status="NOT_ATTEMPTED", persistence_error="") -> dict[str, object]:
    detail = detail_result.detail
    menus = getattr(detail, "menus", ()) if detail else ()
    menu_count = (
        getattr(detail, "menu_count", None)
        if detail else None
    )
    if menu_count is None and detail:
        menu_count = getattr(detail, "declared_menu_count", None)
    review_keywords = getattr(detail, "review_keywords", ()) if detail else ()
    review_mentions = getattr(detail, "review_menu_mentions", ()) if detail else ()
    review_themes = getattr(detail, "review_themes", ()) if detail else ()
    representative_reviews = getattr(detail, "representative_reviews", ()) if detail else ()
    return {
        "restaurant_id": result.reference.restaurant_id,
        "komsco_name": result.reference.komsco_name,
        "komsco_address": result.reference.komsco_address,
        "previous_naver_status": previous,
        "naver_matched_external_name": getattr(naver_reference, "naver_local_name", ""),
        "naver_matched_address": getattr(naver_reference, "naver_local_address", ""),
        "naver_matched_road_address": getattr(naver_reference, "naver_local_road_address", ""),
        "query": result.query,
        "place_id": result.place_id or "",
        "place_url": f"https://pcmap.place.naver.com/restaurant/{result.place_id}/home" if result.place_id else "",
        "resolve_status": result.resolution.status.value,
        "matcher_source": result.matcher_source,
        "qwen_used": result.qwen_used,
        "qwen_confidence": result.qwen_confidence,
        "qwen_ranking": ",".join(str(index) for index in result.qwen_candidate_indices),
        "resolved_rank": (
            result.qwen_candidate_indices.index(result.selected_index) + 1
            if result.resolution.status == ResolutionStatus.RESOLVED
            and result.selected_index in result.qwen_candidate_indices
            else ""
        ),
        "detail_validation_attempts": result.detail_validation_attempts,
        "validation_attempts_json": json.dumps(
            [attempt.__dict__ for attempt in getattr(result, "validation_attempts_detail", ())],
            ensure_ascii=False,
        ),
        "naver_db_fallback_available": previous == "MATCHED",
        "detail_access_method": detail_result.access_method,
        "http_result": detail_result.http_result,
        "playwright_result": detail_result.playwright_result,
        "detail_status": detail_result.status,
        "menu_count": menu_count if menu_count is not None else "",
        "parsed_menu_count": len(menus),
        "menu_complete": (
            getattr(detail, "menu_complete", False)
            if detail else ""
        ),
        "menu_fallback_used": detail_result.menu_fallback_used,
        "home_status": getattr(detail, "home_status", ""),
        "hours_status": getattr(detail, "hours_status", ""),
        "menu_status": getattr(detail, "menu_status", ""),
        "review_status": getattr(detail, "review_status", ""),
        "review_requested": detail_result.review_requested,
        "review_count": len(representative_reviews),
        "review_keyword_count": len(review_keywords),
        "review_menu_mention_count": len(review_mentions),
        "review_theme_count": len(review_themes),
        "representative_review_count": len(representative_reviews),
        "detail_warnings": ";".join(getattr(detail, "warnings", ())) if detail else "",
        "result": "SUCCESS" if result.resolution.status == ResolutionStatus.RESOLVED and detail_result.status == "SUCCESS" else detail_result.status,
        "reason": reason or ";".join(result.resolution.risk_flags),
        "persistence_status": persistence_status,
        "persistence_error": persistence_error,
        "elapsed_ms": elapsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="KOMSCO PCMap detail pipeline")
    parser.add_argument("--restaurant-id", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--crawl-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--force-resolve", action="store_true")
    parser.add_argument("--include-unmatched", action="store_true")
    parser.add_argument("--manifest", type=Path, help="고정 KOMSCO restaurant_id 목록")
    parser.add_argument("--ledger", type=Path, help="terminal 상태 resume ledger")
    parser.add_argument("--status", action="store_true", help="ledger 상태만 출력하고 네트워크/DB 작업을 하지 않음")
    args = parser.parse_args()
    if args.resolve_only and args.crawl_only:
        parser.error("--resolve-only와 --crawl-only는 함께 사용할 수 없습니다")
    if args.write_db and args.report_only:
        parser.error("--write-db와 --report-only는 함께 사용할 수 없습니다")
    root = Path(__file__).resolve().parents[2]
    if args.status:
        if not args.ledger:
            parser.error("--status에는 --ledger 경로가 필요합니다")
        ledger = ResumeLedger(args.ledger, True)
        counts = {}
        for row in ledger.rows.values():
            counts[row.get("status", "UNKNOWN")] = counts.get(row.get("status", "UNKNOWN"), 0) + 1
        print(f"Ledger: {args.ledger}\nRows: {len(ledger.rows)}\n{counts}")
        return 0
    load_local_env(root)
    output = args.output or root / "ai/build/reports/naver-place-pipeline" / f"pipeline-{datetime.now():%Y%m%d-%H%M%S}.csv"
    # The historical checkpoint may contain IDs resolved through the retired
    # NAVER Local fallback.  New Nonhyeon runs use an isolated KOMSCO-only file.
    checkpoint = args.checkpoint or root / "ai/build/reports/naver-place-pipeline/verified-place-ids-komsco-only.csv"
    preflight(root, output, args.write_db, require_resolver=True)
    # Apply an explicit restaurant-id filter before any population limit.  The
    # previous implicit ``limit=1`` optimization could truncate the source
    # before the requested id was selected, producing a misleading zero-target
    # run for ids that were not the first row.
    population_limit = args.limit if args.restaurant_id is None else None
    population = load_komsco_population(
        root, population_limit, matched_only=not args.include_unmatched
    )
    manifest_ids = load_batch_manifest(args.manifest) if args.manifest else None
    requested_ids = manifest_ids if manifest_ids is not None else args.restaurant_id
    refs = select_pipeline_references(
        population.references,
        restaurant_id=requested_ids,
        limit=None if manifest_ids is not None else args.limit,
    )
    if manifest_ids is not None:
        found = {reference.restaurant_id for reference in refs}
        missing = [restaurant_id for restaurant_id in manifest_ids if restaurant_id not in found]
        if missing:
            raise RuntimeError(f"manifest restaurant_id not found in KOMSCO population: {missing[:10]}")
        refs = [next(reference for reference in population.references if reference.restaurant_id == restaurant_id) for restaurant_id in manifest_ids]
        if args.limit is not None:
            refs = refs[: args.limit]
    writer = PipelineWriter(output, args.resume, args.retry_failed)
    completed = writer.completed(args.retry_failed) if args.resume and not args.force_resolve else set()
    ledger_path = args.ledger or (output.with_suffix(".ledger.csv") if args.manifest else None)
    ledger = ResumeLedger(ledger_path, args.resume) if ledger_path else None
    ledger_completed = ledger.completed_ids(retry_failed=args.retry_failed, force_resolve=args.force_resolve) if ledger else set()
    refs = [r for r in refs if r.restaurant_id not in completed and r.restaurant_id not in ledger_completed]
    print(f"Pipeline targets: {len(refs)} (resume skipped: {len(completed)})")
    stations = load_stations(root)
    matcher = QwenCandidateMatcher(OllamaClient())
    verified = load_verified_checkpoint(checkpoint)
    dom_crawler = PlaceDomDetailCrawler()
    limiter = NavigationRateLimiter(
        navigation_delay=float(os.getenv("NAVER_NAVIGATION_DELAY_SECONDS", "2.5")),
        restaurant_delay=float(os.getenv("NAVER_RESTAURANT_DELAY_SECONDS", "5")),
    )
    persistence = PlaceDetailPersistence(root) if args.write_db else None
    stop = False
    def handle_stop(_sig, _frame):
        nonlocal stop
        stop = True
        print("Stopping safely; completed rows are flushed.")
    signal.signal(signal.SIGINT, handle_stop)
    counts: dict[str, int] = {}
    persistence_counts: dict[str, int] = {}
    blocked = False
    started = monotonic()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(); page.set_default_timeout(3_000)
        try:
            for index, reference in enumerate(refs, 1):
                if stop: break
                item_started = monotonic()
                try:
                    station = nearest_station(reference, stations)
                    result = None
                    checkpoint_row = verified.get(reference.restaurant_id)
                    if checkpoint_row and not args.force_resolve:
                        result = checkpoint_result(reference, checkpoint_row)
                    else:
                        for stage, query in (("station", station_query(reference, station)), ("dong", query_for(reference))):
                            result = run_one(
                                page, reference, query, stage, matcher,
                                before_navigation=limiter.before_navigation,
                            )
                            if result.resolution.status == ResolutionStatus.RESOLVED:
                                owner = _existing_place_mapping(root, result.place_id)
                                if owner is None or owner == reference.restaurant_id:
                                    save_verified_checkpoint(checkpoint, result)
                                verified[reference.restaurant_id] = {
                                    "restaurant_id": str(reference.restaurant_id), "place_id": result.place_id,
                                    "resolved_name": result.candidate.name if result.candidate else "",
                                    "resolved_address": result.candidate.address if result.candidate else "",
                                    "verification_status": "RESOLVED",
                                }
                                break
                except RuntimeError as error:
                    if is_blocked_error(error):
                        blocked = True
                        print(f"Stopping batch on service block: {error}")
                        break
                    raise
                assert result is not None
                if (
                    result.place_id
                    and result.resolution.status == ResolutionStatus.RESOLVED
                    and not args.resolve_only
                ):
                    # Resolver validation has already loaded /home.  The DOM
                    # collector reuses that page, then navigates the same page
                    # to menu/list and review/visitor for both report-only and
                    # write-db runs.
                    try:
                        dom_detail = dom_crawler.collect(
                            page, result.place_id, before_navigation=limiter.before_navigation
                        )
                    except PlaywrightTimeoutError as error:
                        dom_detail = None
                        detail_result = SimpleNamespace(
                            status="FAILED",
                            detail=None,
                            menu_fallback_used=False,
                            review_requested=True,
                            access_method="PLAYWRIGHT_DOM",
                            http_result="NOT_ATTEMPTED",
                            playwright_result="TIMEOUT",
                        )
                        detail_error = f"LOCATOR_TIMEOUT: {error}"
                    else:
                        detail_error = ""
                    if dom_detail is None:
                        pass
                    else:
                        detail_result = SimpleNamespace(
                            status=dom_detail.status,
                            detail=dom_detail,
                            menu_fallback_used=False,
                            review_requested=True,
                            access_method="PLAYWRIGHT_DOM",
                            http_result="NOT_ATTEMPTED",
                            playwright_result="SUCCESS" if dom_detail.home_success else "ERROR",
                        )
                else:
                    detail_error = ""
                    detail_result = type(
                        "R",
                        (),
                        {
                            "status": "NOT_ATTEMPTED",
                            "detail": None,
                            "menu_fallback_used": False,
                            "review_requested": False,
                            "access_method": "NONE",
                            "http_result": "NOT_ATTEMPTED",
                            "playwright_result": "NOT_ATTEMPTED",
                        },
                    )()
                persistence_status = "NOT_ATTEMPTED"
                persistence_error = ""
                if args.write_db and result.resolution.status == ResolutionStatus.RESOLVED and detail_result.detail:
                    try:
                        owner = _existing_place_mapping(root, result.place_id)
                        if owner is not None and owner != reference.restaurant_id:
                            raise RuntimeError(
                                f"PLACE_ID_CONFLICT: {result.place_id} already mapped to restaurant {owner}"
                            )
                        write_resolved_to_db(result, root)
                        persistence.persist(
                            reference.restaurant_id,
                            result.place_id,
                            detail_result.detail.to_place_detail(result.place_id),
                        )
                        persistence_status = "SUCCESS"
                    except RuntimeError as error:
                        if is_fatal_persistence_error(error):
                            raise
                        persistence_status = "ERROR"
                        persistence_error = str(error)
                        detail_error = persistence_error
                if ledger:
                    ledger_status = result.resolution.status.value
                    if persistence_status == "ERROR":
                        ledger_status = "PLACE_ID_CONFLICT" if persistence_error.startswith("PLACE_ID_CONFLICT") else "ERROR"
                    ledger.record(
                        reference.restaurant_id,
                        ledger_status,
                        place_id=result.place_id or "",
                        reason=persistence_error or detail_error or ";".join(result.resolution.risk_flags),
                    )
                elapsed = int((monotonic() - item_started) * 1000)
                row = _row(
                    result,
                    population.previous_naver_statuses.get(reference.restaurant_id, "NOT_ENRICHED"),
                    detail_result,
                    elapsed,
                    naver_reference=None,
                    persistence_status=persistence_status,
                    persistence_error=persistence_error or locals().get("detail_error", ""),
                )
                writer.append(row)
                status = result.resolution.status.value
                counts[status] = counts.get(status, 0) + 1
                persistence_counts[persistence_status] = persistence_counts.get(persistence_status, 0) + 1
                total_elapsed = monotonic() - started
                eta = (len(refs) - index) * (total_elapsed / index) if index else 0
                print(f"[{index}/{len(refs)}] {index/len(refs):.1%} restaurant_id={reference.restaurant_id} {reference.komsco_name} {status} {elapsed/1000:.2f}s ETA {time.strftime('%H:%M:%S', time.gmtime(eta))} summary={counts}")
                if index < len(refs):
                    limiter.after_restaurant()
        finally:
            browser.close(); writer.close()
    processed = sum(counts.values())
    print(f"=== Pipeline Summary ===\nProcessed: {processed}\nRemaining: {len(refs) - processed}\n{counts}\nDB persistence: {persistence_counts}\nCSV: {output}")
    return 2 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
