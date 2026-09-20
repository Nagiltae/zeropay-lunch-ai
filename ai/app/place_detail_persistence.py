"""Idempotent MySQL persistence for resolved PCMap detail data."""

# ruff: noqa: E501

from __future__ import annotations

import subprocess
from pathlib import Path

from app.place_detail_models import PlaceDetail
from app.place_resolver_cli import _docker_mysql_command


def _sql(value: object | None) -> str:
    if value is None:
        return "NULL"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def _bounded(value: object | None, max_length: int) -> str | None:
    if value is None:
        return None
    return str(value)[:max_length]


class PlaceDetailPersistence:
    def __init__(self, root: Path):
        self.root = root

    def persist(self, restaurant_id: int, place_id: str, detail: PlaceDetail) -> None:
        if not place_id.isdigit():
            raise ValueError("invalid place id")
        statements = [
            f"""INSERT INTO restaurant_review_summaries
                (restaurant_id,provider,external_place_id,visitor_reviews_total,visitor_reviews_score,
                 visitor_text_review_total,cafe_blog_reviews_total)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(detail.visitor_reviews_total)},
                 {_sql(detail.visitor_reviews_score)},{_sql(detail.visitor_text_review_total)},
                 {_sql(detail.cafe_blog_reviews_total)})
                ON DUPLICATE KEY UPDATE visitor_reviews_total=VALUES(visitor_reviews_total),
                visitor_reviews_score=VALUES(visitor_reviews_score),
                visitor_text_review_total=VALUES(visitor_text_review_total),
                cafe_blog_reviews_total=VALUES(cafe_blog_reviews_total), crawled_at=CURRENT_TIMESTAMP(6)""",
        ]
        for menu in detail.menus:
            statements.append(
                f"""INSERT INTO restaurant_menus
                (restaurant_id,provider,external_place_id,external_menu_id,name,description,price_value,
                 price_text,price_type,menu_type,is_set_menu,thumbnail_url,active)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(menu.external_menu_id)},
                {_sql(_bounded(menu.name, 255))},{_sql(menu.description)},{_sql(menu.price_value)},{_sql(menu.price_text)},
                {_sql(menu.price_type)},{_sql(menu.menu_type)},{_sql(menu.is_set_menu)},
                {_sql(menu.thumbnail_url)},TRUE)
                ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description),
                price_value=VALUES(price_value),price_text=VALUES(price_text),active=TRUE,
                crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        for hour in detail.business_hours:
            statements.append(
                f"""INSERT INTO restaurant_business_hours
                (restaurant_id,provider,external_place_id,day_of_week,open_time,close_time,break_hours,last_order,
                 description,regular_closed_day,irregular_closed_day,business_status)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(hour.day)},{_sql(hour.open_time)},
                {_sql(hour.close_time)},{_sql(hour.break_hours)},{_sql(hour.last_order)},
                {_sql(hour.description)},{_sql(hour.regular_closed_day)},{_sql(hour.irregular_closed_day)},
                {_sql(hour.business_status)})
                ON DUPLICATE KEY UPDATE open_time=VALUES(open_time),close_time=VALUES(close_time),
                break_hours=VALUES(break_hours),last_order=VALUES(last_order),description=VALUES(description),
                crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        for keyword in (*detail.review_keywords, *detail.review_menu_mentions, *detail.voted_keywords):
            statements.append(
                f"""INSERT INTO restaurant_review_keywords
                (restaurant_id,provider,external_place_id,keyword_kind,keyword,mention_count)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(keyword.kind)},
                {_sql(keyword.keyword)},{_sql(keyword.count)})
                ON DUPLICATE KEY UPDATE mention_count=VALUES(mention_count),crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        for review in detail.representative_reviews:
            statements.append(
                f"""INSERT INTO restaurant_representative_reviews
                (restaurant_id,provider,external_place_id,review_id,review_text,review_date,rating)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(review.review_id)},
                {_sql(review.review_text)},{_sql(review.review_date)},{_sql(review.rating)})
                ON DUPLICATE KEY UPDATE review_text=VALUES(review_text),review_date=VALUES(review_date),
                rating=VALUES(rating),crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        self._run("; ".join(statements) + ";")

    def persist_verification(
        self,
        restaurant_id: int,
        status: str,
        reason: str,
        place_id: str | None,
        model_name: str | None,
    ) -> None:
        eligible = "ELIGIBLE" if status == "VERIFIED" else (
            "INELIGIBLE" if reason in {"NON_FOOD", "OUT_OF_SCOPE", "NO_MATCH"} else "UNKNOWN"
        )
        verified_at = "CURRENT_TIMESTAMP(6)" if status == "VERIFIED" else "NULL"
        sql = f"""
            INSERT INTO restaurant_naver_verifications
              (restaurant_id,provider,verification_status,verification_reason,
               external_place_id,model_name,verified_at,last_attempt_at)
            VALUES ({restaurant_id},'NAVER',{_sql(status)},{_sql(reason)},
                    {_sql(place_id)},{_sql(model_name)},{verified_at},CURRENT_TIMESTAMP(6))
            ON DUPLICATE KEY UPDATE verification_status=VALUES(verification_status),
              verification_reason=VALUES(verification_reason),
              external_place_id=VALUES(external_place_id), model_name=VALUES(model_name),
              verified_at=VALUES(verified_at), last_attempt_at=VALUES(last_attempt_at);
            UPDATE restaurants SET recommendation_eligibility={_sql(eligible)}
              WHERE id={restaurant_id};
        """
        self._run(sql)

    @staticmethod
    def preview(detail: PlaceDetail) -> dict[str, int | bool]:
        """Return the write set without opening a database connection."""
        return {
            "menu_rows": len(detail.menus),
            "business_hours_rows": len(detail.business_hours),
            "review_summary": bool(
                detail.visitor_reviews_total is not None
                or detail.visitor_reviews_score is not None
                or detail.visitor_text_review_total is not None
                or detail.cafe_blog_reviews_total is not None
            ),
            "review_keyword_rows": len(
                (*detail.review_keywords, *detail.review_menu_mentions, *detail.voted_keywords)
            ),
            "representative_review_rows": len(detail.representative_reviews),
        }

    def _run(self, sql: str) -> None:
        transactional_sql = f"START TRANSACTION; {sql} COMMIT;"
        try:
            result = subprocess.run(
                _docker_mysql_command(transactional_sql),
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=45,
            )
        except Exception:
            self._rollback()
            raise
        if result.returncode:
            self._rollback()
            detail = (result.stderr or result.stdout or "unknown MySQL error").strip()
            raise RuntimeError(f"detail persistence failed: {detail}")

    def _rollback(self) -> None:
        """Issue an explicit cleanup rollback after a failed mysql client call.

        The failed client connection also rolls back its open InnoDB transaction
        on close; this explicit command keeps the failure path observable and
        safe if the client remains connected in a future implementation.
        """
        try:
            subprocess.run(
                _docker_mysql_command("ROLLBACK;"),
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception:
            pass
