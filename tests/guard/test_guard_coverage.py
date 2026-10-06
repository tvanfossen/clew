"""Tests for clew.guard.coverage (absorbed from doxygen-guard)."""

from clew.guard.coverage import (
    _collect_req_ids,
    _collect_unmapped_functions,
    format_coverage_json,
    format_coverage_markdown,
    format_coverage_text,
)
from clew.guard.tags import TaggedFunction


class TestCollectReqIds:
    def test_basic(self):
        funcs = [
            TaggedFunction(name="a", file_path="a.c", reqs=["REQ-001", "REQ-002"]),
            TaggedFunction(name="b", file_path="b.c", reqs=["REQ-002", "REQ-003"]),
        ]
        assert _collect_req_ids(funcs) == {"REQ-001", "REQ-002", "REQ-003"}

    def test_empty(self):
        assert _collect_req_ids([]) == set()


class TestCollectUnmapped:
    def test_no_reqs(self):
        funcs = [
            TaggedFunction(name="a", file_path="a.c", reqs=["REQ-001"]),
            TaggedFunction(name="b", file_path="b.c"),
        ]
        assert _collect_unmapped_functions(funcs) == {"b"}

    def test_exempt_functions_are_not_unmapped(self):
        """Any exemption tag excludes a function, not just the old @internal spelling."""
        funcs = [
            TaggedFunction(name="helper", file_path="a.c", is_exempt=True),
            TaggedFunction(name="public_api", file_path="a.c"),
        ]
        assert _collect_unmapped_functions(funcs) == {"public_api"}


class TestFormatters:
    REPORT = {
        "total_requirements": 3,
        "covered": ["REQ-001"],
        "uncovered": ["REQ-002"],
        "orphan_refs": ["REQ-999"],
        "unmapped_functions": ["helper"],
    }

    def test_text_format(self):
        result = format_coverage_text(self.REPORT)
        assert "1/3" in result
        assert "REQ-002" in result
        assert "REQ-999" in result

    def test_json_format(self):
        result = format_coverage_json(self.REPORT)
        assert '"total_requirements": 3' in result

    def test_markdown_format(self):
        result = format_coverage_markdown(self.REPORT)
        assert "# Requirements Coverage" in result
        assert "REQ-002" in result
