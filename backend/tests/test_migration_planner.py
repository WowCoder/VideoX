import unittest

from app.services.migration_planner import plan_script_splits, split_project_id


class WorkspaceMigrationPlannerTests(unittest.TestCase):
    def test_selected_script_remains_on_original_project(self):
        plan = plan_script_splits(
            "project-a",
            [
                {"id": "script-new", "updated_at": "2026-08-18T10:00:00Z"},
                {"id": "script-selected", "updated_at": "2026-08-01T10:00:00Z"},
                {"id": "script-snapshot", "is_snapshot": True, "updated_at": "2026-08-19T10:00:00Z"},
            ],
            selected_script_id="script-selected",
        )
        self.assertEqual(plan["primary_script_id"], "script-selected")
        self.assertEqual(
            [item["script_id"] for item in plan["splits"]],
            ["script-new", "script-snapshot"],
        )
        self.assertEqual(plan["splits"][1]["recovery_kind"], "snapshot")

    def test_newest_business_script_wins_without_selection(self):
        plan = plan_script_splits(
            "project-a",
            [
                {"id": "older", "updated_at": "2026-01-01T00:00:00Z"},
                {"id": "newer", "updated_at": "2026-02-01T00:00:00Z"},
                {"id": "snapshot", "is_snapshot": True, "updated_at": "2026-03-01T00:00:00Z"},
            ],
        )
        self.assertEqual(plan["primary_script_id"], "newer")
        self.assertEqual(len(plan["splits"]), 2)

    def test_split_ids_are_stable_and_project_scoped(self):
        first = split_project_id("project-a", "script-1")
        self.assertEqual(first, split_project_id("project-a", "script-1"))
        self.assertNotEqual(first, split_project_id("project-b", "script-1"))
        self.assertNotEqual(first, split_project_id("project-a", "script-2"))

    def test_empty_project_gets_no_synthetic_split(self):
        self.assertEqual(
            plan_script_splits("project-a", []),
            {"primary_script_id": None, "splits": []},
        )


if __name__ == "__main__":
    unittest.main()
