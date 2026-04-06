"""Tests for section-level work_projects.md patching."""

from physi_core.memory.work_projects_patch import apply_work_project_patch


class TestApplyWorkProjectPatch:
    def test_add_to_empty(self) -> None:
        out = apply_work_project_patch("", "A", "add", "- line1\n- line2")
        assert "## A" in out
        assert "- line1" in out

    def test_add_duplicate_raises(self) -> None:
        base = "# Title\n\n## A\nx\n"
        try:
            apply_work_project_patch(base, "A", "add", "y")
        except ValueError as e:
            assert "已存在" in str(e)
        else:
            raise AssertionError("expected ValueError")

    def test_update(self) -> None:
        base = "## Foo\nold\n"
        out = apply_work_project_patch(base, "Foo", "update", "new")
        assert "new" in out
        assert "old" not in out

    def test_remove(self) -> None:
        base = "## X\na\n\n## Y\nb\n"
        out = apply_work_project_patch(base, "X", "remove", "")
        assert "## X" not in out
        assert "## Y" in out

    def test_preamble_preserved(self) -> None:
        base = "# Doc\n\nintro\n\n## P\nbody\n"
        out = apply_work_project_patch(base, "P", "update", "z")
        assert "# Doc" in out
        assert "intro" in out
        assert "z" in out
