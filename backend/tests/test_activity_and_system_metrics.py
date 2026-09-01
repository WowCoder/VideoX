import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api.activity import HEARTBEAT_WRITE_INTERVAL
from app.models.monitoring import SystemMetricSnapshot, UserDailyActivity
from app.services.system_metrics import collect_system_metrics


class UserActivityContractTests(unittest.TestCase):
    def test_activity_is_unique_per_user_and_shanghai_day(self):
        names = {constraint.name for constraint in UserDailyActivity.__table__.constraints}
        self.assertIn("uq_user_daily_activity_user_date", names)
        self.assertEqual(int(HEARTBEAT_WRITE_INTERVAL.total_seconds()), 900)


class SystemMetricContractTests(unittest.TestCase):
    def test_snapshot_has_node_and_status_indexes(self):
        names = {index.name for index in SystemMetricSnapshot.__table__.indexes}
        self.assertIn("ix_system_metric_node_collected", names)
        self.assertIn("ix_system_metric_status_collected", names)

    def test_collector_calculates_memory_disk_and_normalized_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meminfo = root / "meminfo"
            uptime = root / "uptime"
            meminfo.write_text(
                "MemTotal:       1000 kB\nMemAvailable:    400 kB\n",
                encoding="utf-8",
            )
            uptime.write_text("90061.25 0.00\n", encoding="utf-8")
            disk = shutil._ntuple_diskusage(total=1000, used=750, free=250)
            with (
                patch("app.services.system_metrics.os.getloadavg", return_value=(1.5, 1.0, 0.5)),
                patch("app.services.system_metrics._cpu_count", return_value=4),
                patch("app.services.system_metrics._cgroup_memory_limit_bytes", return_value=None),
                patch("app.services.system_metrics.shutil.disk_usage", return_value=disk),
            ):
                result = collect_system_metrics(
                    disk_path=temp_dir,
                    metric_scope="host",
                    meminfo_path=str(meminfo),
                    uptime_path=str(uptime),
                )
        self.assertEqual(result["metric_scope"], "host")
        self.assertEqual(result["cpu_count"], 4)
        self.assertEqual(result["memory_total_bytes"], 1000 * 1024)
        self.assertEqual(result["memory_used_bytes"], 600 * 1024)
        self.assertEqual(result["memory_percent"], 60.0)
        self.assertEqual(result["disk_percent"], 75.0)
        self.assertEqual(result["uptime_seconds"], 90061)

    def test_collector_rejects_missing_disk_monitor_directory(self):
        with self.assertRaisesRegex(RuntimeError, "磁盘监控目录不可用"):
            collect_system_metrics(
                disk_path="/definitely/not/an/openvma/metrics/path",
                metric_scope="host",
            )


if __name__ == "__main__":
    unittest.main()
