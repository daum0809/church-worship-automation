import tempfile
import unittest
from datetime import date
from pathlib import Path

import pymupdf
import yaml

from tools.release_guard import ReleaseBlocked, verify


class ReleaseGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "hymns").mkdir()
        self.data = {
            "날짜": "2026-10-25", "교회소식": "이번 주 안내",
            "입례찬송": {"장": 64, "제목": "기뻐하며 경배하세", "악보": False},
            "영광송": {"장": 76, "제목": "창조의 주 아버지께"},
            "찬송": {"장": 478, "제목": "참 아름다워라"},
            "봉헌찬송": {"장": 218, "제목": "네 맘과 정성을 다하여서"},
            "대표기도": {"이름": "기도자"},
            "성경봉독": {"봉독자": "봉독자", "본문": "눅 10:36", "말씀": "36 본문"},
            "찬양": {"곡명": "찬양"}, "말씀": {"제목": "설교", "설교자": "목사"},
        }
        for n in (76, 478, 218):
            doc = pymupdf.open()
            doc.new_page(width=960, height=540)
            doc.save(self.root / "hymns" / f"{n:03d}.pdf")
            doc.close()
        self.write()

    def write(self):
        (self.root / "weekly.yaml").write_text(
            yaml.safe_dump(self.data, allow_unicode=True), encoding="utf-8"
        )

    def check(self, **kwargs):
        return verify(self.root / "weekly.yaml", today=date(2026, 10, 20), **kwargs)

    def test_valid(self):
        self.assertEqual(len(self.check()), 3)

    def test_stale(self):
        self.data["날짜"] = "2026-10-11"
        self.write()
        with self.assertRaisesRegex(ReleaseBlocked, "오래된"):
            self.check()

    def test_news(self):
        self.data["교회소식"] = ""
        self.write()
        with self.assertRaisesRegex(ReleaseBlocked, "교회소식"):
            self.check()

    def test_missing_hymn(self):
        (self.root / "hymns" / "218.pdf").unlink()
        with self.assertRaisesRegex(ReleaseBlocked, "악보 PDF 없음"):
            self.check()

    def test_bad_ratio(self):
        path = self.root / "hymns" / "218.pdf"
        path.unlink()
        doc = pymupdf.open()
        doc.new_page(width=500, height=500)
        doc.save(path)
        doc.close()
        with self.assertRaisesRegex(ReleaseBlocked, "16:9"):
            self.check()

    def test_cache_only(self):
        self.data["날짜"] = "2026-10-11"
        self.data["교회소식"] = ""
        self.write()
        self.assertEqual(len(self.check(cache_only=True)), 3)

    def test_missing_title(self):
        self.data["찬송"]["제목"] = ""
        self.write()
        with self.assertRaisesRegex(ReleaseBlocked, "제목 누락"):
            self.check()

    def test_bad_number(self):
        self.data["찬송"]["장"] = 999
        self.write()
        with self.assertRaisesRegex(ReleaseBlocked, "범위 오류"):
            self.check()

    def test_required_sermon(self):
        self.data["말씀"]["제목"] = ""
        self.write()
        with self.assertRaisesRegex(ReleaseBlocked, "말씀.제목"):
            self.check()

    def test_corrupt_pdf(self):
        (self.root / "hymns" / "218.pdf").write_bytes(b"not pdf")
        with self.assertRaisesRegex(ReleaseBlocked, "손상"):
            self.check()


if __name__ == "__main__":
    unittest.main()
