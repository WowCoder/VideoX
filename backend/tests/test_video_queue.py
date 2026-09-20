import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Settings
from app.services.video_queue import (
    prioritized_video_candidates,
    round_robin_video_candidates,
    wake_video_scheduler,
)


class VideoQueueConfigurationTests(unittest.TestCase):
    def test_defaults_allow_a_complete_maximum_size_project(self):
        settings = Settings(_env_file=None)

        self.assertEqual(settings.video_batch_max_shots, 2000)
        self.assertGreaterEqual(
            settings.video_queue_max_per_project,
            settings.video_batch_max_shots,
        )

    def test_rejects_batch_limit_larger_than_project_queue(self):
        with self.assertRaisesRegex(ValidationError, "VIDEO_BATCH_MAX_SHOTS"):
            Settings(
                _env_file=None,
                video_batch_max_shots=101,
                video_queue_max_per_project=100,
            )

    def test_rejects_project_inflight_larger_than_user_inflight(self):
        with self.assertRaisesRegex(ValidationError, "VIDEO_INFLIGHT_MAX_PER_PROJECT"):
            Settings(
                _env_file=None,
                video_inflight_max_per_project=3,
                video_inflight_max_per_user=2,
            )


class VideoQueueFairnessTests(unittest.TestCase):
    def test_plan_priority_precedes_lower_tiers_and_preserves_tier_fairness(self):
        candidates = [
            SimpleNamespace(id="low-1", batch_id="low", owner_id="free"),
            SimpleNamespace(id="high-a1", batch_id="high-a", owner_id="team"),
            SimpleNamespace(id="high-a2", batch_id="high-a", owner_id="team"),
            SimpleNamespace(id="high-b1", batch_id="high-b", owner_id="studio"),
        ]

        result = prioritized_video_candidates(candidates, {"free": 9, "team": 0, "studio": 0})

        self.assertEqual([item.id for item in result], ["high-a1", "high-b1", "high-a2", "low-1"])

    def test_interleaves_batches_while_preserving_each_batch_order(self):
        candidates = [
            SimpleNamespace(id="a1", batch_id="a"),
            SimpleNamespace(id="a2", batch_id="a"),
            SimpleNamespace(id="a3", batch_id="a"),
            SimpleNamespace(id="b1", batch_id="b"),
            SimpleNamespace(id="b2", batch_id="b"),
        ]

        result = round_robin_video_candidates(candidates)

        self.assertEqual([item.id for item in result], ["a1", "b1", "a2", "b2", "a3"])

    def test_single_batch_keeps_original_order(self):
        candidates = [
            SimpleNamespace(id="a1", batch_id="a"),
            SimpleNamespace(id="a2", batch_id="a"),
        ]

        self.assertEqual(
            [item.id for item in round_robin_video_candidates(candidates)],
            ["a1", "a2"],
        )


class VideoSchedulerWakeTests(unittest.TestCase):
    def test_broker_outage_is_left_for_beat_without_raising_to_api(self):
        with self.assertLogs("app.services.video_queue", level="WARNING"), patch(
                "app.tasks.video_tasks.schedule_video_jobs.apply_async",
                side_effect=RuntimeError("redis offline"),
            ):
                self.assertFalse(wake_video_scheduler())


if __name__ == "__main__":
    unittest.main()
