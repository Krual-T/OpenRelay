"""测试 StreamController 和 PlanStreamController。"""

from openrelay.presentation.v2_renderer.cells import AgentMessageCell, ProposedPlanCell
from openrelay.presentation.v2_renderer.stream_controller import (
    PlanStreamController,
    StreamController,
)


class TestStreamController:
    def test_push_splits_lines(self):
        sc = StreamController()
        cells = sc.push("Hello\nWorld\n")
        assert len(cells) == 2
        assert cells[0].source_line == "Hello"
        assert cells[0].is_first is True
        assert cells[1].source_line == "World"
        assert cells[1].is_first is False

    def test_push_incremental_builds_line(self):
        sc = StreamController()
        cells1 = sc.push("Hello ")
        assert cells1 == []

        cells2 = sc.push("World\n")
        assert len(cells2) == 1
        assert cells2[0].source_line == "Hello World"

    def test_push_multiple_deltas(self):
        sc = StreamController()
        sc.push("Line 1\nLine ")
        cells = sc.push("2\nLine 3\n")
        assert len(cells) == 2
        assert cells[0].source_line == "Line 2"
        assert cells[1].source_line == "Line 3"

    def test_push_empty_delta(self):
        sc = StreamController()
        cells = sc.push("")
        assert cells == []

    def test_finalize_returns_remaining_and_raw_source(self):
        sc = StreamController()
        sc.push("Line 1\nLine 2\nUnfinished")
        cells, raw = sc.finalize()
        assert len(cells) == 1
        assert cells[0].source_line == "Unfinished"
        assert raw == "Line 1\nLine 2\nUnfinished"

    def test_finalize_resets_state(self):
        sc = StreamController()
        sc.push("Hello\n")
        sc.finalize()
        assert sc.raw_source == ""
        assert sc.emitted_len == 0
        assert sc.is_first is True

    def test_multiple_finalize_cycles(self):
        sc = StreamController()
        cells1, raw1 = sc.finalize()
        assert cells1 == []
        assert raw1 == ""

        # push emits cells during streaming; finalize only catches unfinished content
        emitted = sc.push("New\n")
        assert len(emitted) == 1
        cells2, raw2 = sc.finalize()
        assert cells2 == []  # nothing left after push() already emitted
        assert "New" in raw2

    def test_blank_lines_skipped(self):
        sc = StreamController()
        cells = sc.push("\n\nHello\n\nWorld\n")
        assert len(cells) == 2
        assert cells[0].source_line == "Hello"
        assert cells[1].source_line == "World"


class TestPlanStreamController:
    def test_push_accumulates(self):
        psc = PlanStreamController()
        psc.push("# Plan\n")
        psc.push("Step 1\n")
        assert psc.raw_source == "# Plan\nStep 1\n"

    def test_finalize_returns_proposed_plan_cell(self):
        psc = PlanStreamController()
        psc.push("# Plan\nStep 1")
        cell = psc.finalize()
        assert isinstance(cell, ProposedPlanCell)
        assert cell.source == "# Plan\nStep 1"

    def test_finalize_empty_returns_none(self):
        psc = PlanStreamController()
        cell = psc.finalize()
        assert cell is None

    def test_finalize_resets(self):
        psc = PlanStreamController()
        psc.push("content")
        psc.finalize()
        assert psc.raw_source == ""
