"""확정된 PCMap 상세 데이터를 section별로 안전하게 upsert하는 persistence."""

# ruff: noqa: E501

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from app.entity_resolution.verification_quality_gate import source_fingerprint
from app.naver.place_detail_models import PlaceDetail
from app.naver.place_resolver_cli import _docker_mysql_command


def _sql(value: object | None) -> str:
    if value is None:
        return "NULL"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def _bounded(value: object | None, max_length: int) -> str | None:
    if value is None:
        return None
    return str(value)[:max_length]


class MysqlWriteSession:
    """기존 mysql CLI를 batch 동안 유지하되 transaction은 호출별로 분리한다."""

    def __init__(self, root: Path):
        self.root = root
        self.process = None

    def _start(self):
        command = [
            "docker", "compose", "exec", "-T", "mysql", "sh", "-c",
            'MYSQL_PWD="$MYSQL_PASSWORD" mysql --batch --skip-column-names --raw '
            '--unbuffered --default-character-set=utf8mb4 -u "$MYSQL_USER" "$MYSQL_DATABASE"',
        ]
        self.process = subprocess.Popen(
            command,
            cwd=self.root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def __enter__(self):
        self._start()
        return self

    def execute(self, sql: str) -> None:
        if self.process is None:
            self._start()
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("MySQL write session is not open")
        marker = f"__ZERO_PAY_BATCH_{uuid.uuid4().hex}__"
        self.process.stdin.write(f"{sql.rstrip(';')}; SELECT '{marker}';\n")
        self.process.stdin.flush()
        for line in self.process.stdout:
            if line.strip() == marker:
                return
        stderr = self.process.stderr.read() if self.process.stderr else ""
        raise RuntimeError(f"MySQL persistent session failed: {stderr.strip()}")

    def close(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=15)
        except Exception:
            self.process.kill()
            self.process.wait()
        finally:
            self.process = None

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class PlaceDetailPersistence:
    def __init__(self, root: Path, write_session: MysqlWriteSession | None = None):
        self.root = root
        self.write_session = write_session

    def persist(
        self, restaurant_id: int, place_id: str, detail: PlaceDetail,
        sections: dict[str, bool] | None = None,
        section_states: dict[str, str] | None = None,
    ) -> None:
        if not place_id.isdigit():
            raise ValueError("invalid place id")
        selected = sections or {"review": True, "menu": True, "business_hours": True}
        statements = []
        # 리뷰 페이지에 정상 접근했지만 실제 리뷰 요약이 없는 ABSENT_CONFIRMED에서는
        # 새 NULL 값으로 기존 summary를 덮어쓰지 않는다. 페이지 접근 실패(FAILED)는
        # 애초에 review section을 쓰지 않으므로 기존 데이터가 유지된다.
        review_snapshot_success = not section_states or section_states.get("review") == "SUCCESS"
        if selected["review"] and review_snapshot_success:
            statements.append(f"""INSERT INTO restaurant_review_summaries
                (restaurant_id,provider,external_place_id,visitor_reviews_total,visitor_reviews_score,
                 visitor_text_review_total,cafe_blog_reviews_total)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(detail.visitor_reviews_total)},
                 {_sql(detail.visitor_reviews_score)},{_sql(detail.visitor_text_review_total)},
                 {_sql(detail.cafe_blog_reviews_total)})
                ON DUPLICATE KEY UPDATE visitor_reviews_total=VALUES(visitor_reviews_total),
                visitor_reviews_score=VALUES(visitor_reviews_score),
                visitor_text_review_total=VALUES(visitor_text_review_total),
                cafe_blog_reviews_total=VALUES(cafe_blog_reviews_total), crawled_at=CURRENT_TIMESTAMP(6)""")
        for menu in detail.menus if selected["menu"] else ():
            statements.append(
                f"""INSERT INTO restaurant_menus
                (restaurant_id,provider,external_place_id,external_menu_id,name,description,price_value,
                 price_text,price_type,menu_type,is_set_menu,thumbnail_url,active)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(menu.external_menu_id)},
                {_sql(_bounded(menu.name, 255))},{_sql(menu.description)},{_sql(menu.price_value)},{_sql(menu.price_text)},
                {_sql(menu.price_type)},{_sql(menu.menu_type)},{_sql(menu.is_set_menu)},
                {_sql(menu.thumbnail_url)},TRUE)
                ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description),
                price_value=COALESCE(VALUES(price_value),price_value),
                price_text=COALESCE(VALUES(price_text),price_text),active=TRUE,
                crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        for hour in detail.business_hours if selected["business_hours"] else ():
            statements.append(
                f"""INSERT INTO restaurant_business_hours
                (restaurant_id,provider,external_place_id,day_of_week,open_time,close_time,break_hours,last_order,
                 description,regular_closed_day,irregular_closed_day,business_status,active)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(hour.day)},{_sql(hour.open_time)},
                {_sql(hour.close_time)},{_sql(hour.break_hours)},{_sql(hour.last_order)},
                {_sql(hour.description)},{_sql(hour.regular_closed_day)},{_sql(hour.irregular_closed_day)},
                {_sql(hour.business_status)},TRUE)
                ON DUPLICATE KEY UPDATE open_time=VALUES(open_time),close_time=VALUES(close_time),
                break_hours=VALUES(break_hours),last_order=VALUES(last_order),description=VALUES(description),
                business_status=VALUES(business_status),active=TRUE,crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        for keyword in (
            (*detail.review_keywords, *detail.review_menu_mentions, *detail.voted_keywords)
            if selected["review"] else ()
        ):
            statements.append(
                f"""INSERT INTO restaurant_review_keywords
                (restaurant_id,provider,external_place_id,keyword_kind,keyword,mention_count,active)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(keyword.kind)},
                {_sql(keyword.keyword)},{_sql(keyword.count)},TRUE)
                ON DUPLICATE KEY UPDATE mention_count=VALUES(mention_count),active=TRUE,
                crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        for review in detail.representative_reviews if selected["review"] else ():
            statements.append(
                f"""INSERT INTO restaurant_representative_reviews
                (restaurant_id,provider,external_place_id,review_id,review_text,review_date,rating,active)
                VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(review.review_id)},
                {_sql(review.review_text)},{_sql(review.review_date)},{_sql(review.rating)},TRUE)
                ON DUPLICATE KEY UPDATE review_text=VALUES(review_text),review_date=VALUES(review_date),
                rating=VALUES(rating),active=TRUE,crawled_at=CURRENT_TIMESTAMP(6)"""
            )
        if section_states:
            statements.extend(
                self._section_state_statements(
                    restaurant_id, place_id, detail, selected, section_states
                )
            )
        if statements:
            self._run("; ".join(statements) + ";")

    def _section_state_statements(
        self,
        restaurant_id: int,
        place_id: str,
        detail: PlaceDetail,
        selected: dict[str, bool],
        section_states: dict[str, str],
    ) -> list[str]:
        statements = []
        for section, state in section_states.items():
            statements.append(self._section_state_upsert(restaurant_id, place_id, section, state))
        if section_states.get("menu") in {"SUCCESS", "ABSENT_CONFIRMED"} and selected.get("menu"):
            ids = tuple(menu.external_menu_id for menu in detail.menus)
            statements.append(self._deactivate_missing("restaurant_menus", "external_menu_id", ids, place_id))
        if section_states.get("business_hours") in {"SUCCESS", "ABSENT_CONFIRMED"} and selected.get("business_hours"):
            days = tuple(hour.day for hour in detail.business_hours)
            statements.append(self._deactivate_missing("restaurant_business_hours", "day_of_week", days, place_id))
        if section_states.get("review") in {"SUCCESS", "ABSENT_CONFIRMED"} and selected.get("review"):
            keywords = tuple(
                (keyword.kind, keyword.keyword)
                for keyword in (*detail.review_keywords, *detail.review_menu_mentions, *detail.voted_keywords)
            )
            keyword_condition = " OR ".join(
                f"(keyword_kind={_sql(kind)} AND keyword={_sql(keyword)})"
                for kind, keyword in keywords
            ) or "FALSE"
            statements.append(
                f"UPDATE restaurant_review_keywords SET active=FALSE WHERE provider='NAVER' "
                f"AND external_place_id={_sql(place_id)} AND active=TRUE AND NOT ({keyword_condition})"
            )
            review_ids = tuple(review.review_id for review in detail.representative_reviews)
            statements.append(self._deactivate_missing("restaurant_representative_reviews", "review_id", review_ids, place_id))
        return statements

    def persist_section_states(
        self, restaurant_id: int, place_id: str, section_states: dict[str, str]
    ) -> None:
        if not place_id.isdigit():
            raise ValueError("invalid place id")
        if section_states:
            self._run(
                "; ".join(
                    self._section_state_upsert(restaurant_id, place_id, section, state)
                    for section, state in section_states.items()
                )
                + ";"
            )

    @staticmethod
    def _section_state_upsert(
        restaurant_id: int, place_id: str, section: str, state: str
    ) -> str:
        if state not in {"SUCCESS", "ABSENT_CONFIRMED", "FAILED"}:
            raise ValueError(f"invalid detail section state: {state}")
        return f"""INSERT INTO restaurant_detail_section_states
            (restaurant_id,provider,external_place_id,section,state,error_code)
            VALUES ({restaurant_id},'NAVER',{_sql(place_id)},{_sql(section)},{_sql(state)},NULL)
            ON DUPLICATE KEY UPDATE restaurant_id=VALUES(restaurant_id),state=VALUES(state),
            checked_at=CURRENT_TIMESTAMP(6),error_code=VALUES(error_code)"""

    @staticmethod
    def _deactivate_missing(table: str, key: str, values: tuple[str, ...], place_id: str) -> str:
        condition = "FALSE" if not values else f"{key} NOT IN ({','.join(_sql(value) for value in values)})"
        return (
            f"UPDATE {table} SET active=FALSE WHERE provider='NAVER' "
            f"AND external_place_id={_sql(place_id)} AND active=TRUE AND {condition}"
        )

    def verification_sql(
        self,
        restaurant_id: int,
        status: str,
        reason: str,
        place_id: str | None,
        model_name: str | None,
        source: dict[str, object] | None = None,
        source_fingerprint_value: str | None = None,
        search_policy_version: str | None = None,
        eligibility: str | None = None,
    ) -> str:
        # 검증 fingerprint와 detail section은 별도 계약이므로 한쪽 갱신이 다른 상태를 삭제하지 않는다.
        eligible = eligibility or ("ELIGIBLE" if status == "VERIFIED" else (
            "INELIGIBLE" if reason in {"NON_FOOD", "OUT_OF_SCOPE", "NO_MATCH"} else "UNKNOWN"
        ))
        if eligible not in {"ELIGIBLE", "INELIGIBLE", "UNKNOWN"}:
            raise ValueError("invalid recommendation eligibility")
        verified_at = "CURRENT_TIMESTAMP(6)" if status == "VERIFIED" else "NULL"
        sql = f"""
            INSERT INTO restaurant_naver_verifications
              (restaurant_id,provider,verification_status,verification_reason,
               source_fingerprint,search_policy_version,external_place_id,model_name,verified_at,last_attempt_at)
            VALUES ({restaurant_id},'NAVER',{_sql(status)},{_sql(reason)},
                    {_sql(source_fingerprint_value or (source_fingerprint(source) if source else None))},
                    {_sql(search_policy_version)},
                    {_sql(place_id)},{_sql(model_name)},{verified_at},CURRENT_TIMESTAMP(6))
            ON DUPLICATE KEY UPDATE verification_status=VALUES(verification_status),
              verification_reason=VALUES(verification_reason),
              source_fingerprint=VALUES(source_fingerprint),
              search_policy_version=VALUES(search_policy_version),
              external_place_id=VALUES(external_place_id), model_name=VALUES(model_name),
              verified_at=VALUES(verified_at), last_attempt_at=VALUES(last_attempt_at);
            UPDATE restaurants SET recommendation_eligibility={_sql(eligible)}
              WHERE id={restaurant_id};
        """
        return sql

    def persist_verification(
        self,
        restaurant_id: int,
        status: str,
        reason: str,
        place_id: str | None,
        model_name: str | None,
        source: dict[str, object] | None = None,
        source_fingerprint_value: str | None = None,
        search_policy_version: str | None = None,
        eligibility: str | None = None,
    ) -> None:
        self._run(self.verification_sql(
            restaurant_id=restaurant_id,
            status=status,
            reason=reason,
            place_id=place_id,
            model_name=model_name,
            source=source,
            source_fingerprint_value=source_fingerprint_value,
            search_policy_version=search_policy_version,
            eligibility=eligibility,
        ))

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
        if self.write_session is not None:
            try:
                self.write_session.execute(transactional_sql)
            except Exception:
                # 실패한 client는 열린 transaction과 함께 폐기하고 다음 row에서 재연결한다.
                self.write_session.close()
                raise
            return
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
