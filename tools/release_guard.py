"""광염교회 예배자료 발행 전 차단 검사.

기존 worship/build.py는 악보가 없어도 PDF를 저장할 수 있으므로,
최종 발행 워크플로에서는 반드시 이 검사를 먼저 실행한다.
이 검사는 PDF 파일의 구조만 확인하며 악보·가사 시각 정렬을 보증하지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pymupdf
import yaml

HYMN_SECTIONS = ("입례찬송", "영광송", "찬송", "봉헌찬송")
REQUIRED = (
    ("대표기도", "이름"),
    ("성경봉독", "봉독자"),
    ("성경봉독", "본문"),
    ("성경봉독", "말씀"),
    ("찬양", "곡명"),
    ("말씀", "제목"),
    ("말씀", "설교자"),
)


class ReleaseBlocked(ValueError):
    pass


def upcoming_sunday(today: date) -> date:
    return today + timedelta(days=(6 - today.weekday()) % 7)


def verify(weekly="weekly.yaml", *, root=None, today=None, cache_only=False):
    weekly = Path(weekly)
    root = Path(root) if root is not None else weekly.parent
    if not weekly.is_file():
        raise ReleaseBlocked(f"주간 입력 파일 없음: {weekly}")
    try:
        data = yaml.safe_load(weekly.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReleaseBlocked(f"주간 입력을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseBlocked("주간 입력 최상위 형식 오류")

    if not cache_only:
        today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
        expected = upcoming_sunday(today)
        raw = data.get("날짜")
        try:
            chosen = expected if raw in (None, "") else (
                raw.date() if isinstance(raw, datetime) else (
                    raw if isinstance(raw, date) else date.fromisoformat(str(raw).strip())
                )
            )
        except (TypeError, ValueError) as exc:
            raise ReleaseBlocked(f"예배 날짜 형식 오류: {raw}") from exc
        if chosen != expected:
            raise ReleaseBlocked(f"예배 날짜 {chosen} / 이번 주일 {expected}: 오래된 자료 발행 차단")
        for section, field in REQUIRED:
            item = data.get(section)
            value = item.get(field) if isinstance(item, dict) else None
            if not isinstance(value, str) or not value.strip():
                raise ReleaseBlocked(f"필수 정보 누락: {section}.{field}")
        news = data.get("교회소식")
        if not isinstance(news, str) or not news.strip():
            raise ReleaseBlocked("교회소식 누락: 이전 주 안내 재사용 차단")

    checked = {}
    for section in HYMN_SECTIONS:
        item = data.get(section)
        if not isinstance(item, dict):
            raise ReleaseBlocked(f"{section}: 정보 없음")
        try:
            number = int(item["장"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ReleaseBlocked(f"{section}: 찬송가 번호 오류") from exc
        if not 1 <= number <= 645:
            raise ReleaseBlocked(f"{section}: 찬송가 번호 범위 오류 ({number})")
        if not isinstance(item.get("제목"), str) or not item["제목"].strip():
            raise ReleaseBlocked(f"{section}: 찬송가 제목 누락")
        if section == "입례찬송" and item.get("악보") is False:
            continue
        path = root / "hymns" / f"{number:03d}.pdf"
        if not path.is_file():
            raise ReleaseBlocked(f"{section}: {number}장 악보 PDF 없음: {path}")
        try:
            with pymupdf.open(path) as pdf:
                if pdf.page_count < 1:
                    raise ReleaseBlocked(f"{number}장: 빈 PDF")
                for index, page in enumerate(pdf, 1):
                    if page.rect.height <= 0 or not 1.70 <= page.rect.width / page.rect.height <= 1.85:
                        raise ReleaseBlocked(f"{number}장 {index}쪽: 16:9 화면비율 오류")
                checked[number] = pdf.page_count
        except (pymupdf.FileDataError, pymupdf.EmptyFileError, ZeroDivisionError) as exc:
            raise ReleaseBlocked(f"{number}장: 악보 PDF 손상") from exc
    return checked


def main():
    parser = argparse.ArgumentParser(description="광염교회 예배 발행 전 필수 검사")
    parser.add_argument("weekly", nargs="?", default="weekly.yaml")
    parser.add_argument("--cache-only", action="store_true", help="오래된 주간 입력과 무관하게 악보 파일 구조만 확인")
    args = parser.parse_args()
    try:
        result = verify(args.weekly, cache_only=args.cache_only)
    except ReleaseBlocked as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: 악보 {len(result)}곡, 총 {sum(result.values())}쪽의 기본 파일 구조 검사")
    print("미검증: 악보 한 줄 아래 가사 한 줄, 페이지당 두 묶음, 절당 네 줄, 음표·가사 대응")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
