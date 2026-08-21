import unittest

from app.api.jobs import _job_can_delete


class JobLifecycleRuleTests(unittest.TestCase):
    def test_running_and_queued_jobs_must_be_paused_before_deletion(self):
        self.assertFalse(_job_can_delete("QUEUED"))
        self.assertFalse(_job_can_delete("RUNNING"))

    def test_terminal_and_paused_jobs_can_be_deleted(self):
        for status in ("SUCCEEDED", "FAILED", "PAUSED", "CANCELLED"):
            with self.subTest(status=status):
                self.assertTrue(_job_can_delete(status))


if __name__ == "__main__":
    unittest.main()
