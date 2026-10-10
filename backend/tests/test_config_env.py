"""Exercise environment loading without depending on a developer's private .env."""

import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from app.config import Settings


class EnvironmentLoadingTests(unittest.TestCase):
    def test_repository_env_is_loaded_from_an_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "backend" / "app" / "config.py"
            config.parent.mkdir(parents=True)
            shutil.copyfile(Path(__file__).parents[1] / "app" / "config.py", config)
            (root / ".env").write_text("CELERY_TASK_DEFAULT_QUEUE=fixture-root-queue\n", encoding="utf-8")
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            (elsewhere / ".env").write_text("CELERY_TASK_DEFAULT_QUEUE=wrong-cwd-queue\n", encoding="utf-8")
            spec = importlib.util.spec_from_file_location("fixture_config", config)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            previous = Path.cwd()
            try:
                os.chdir(elsewhere)
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(module.Settings().celery_task_default_queue, "fixture-root-queue")
                    self.assertEqual(module.Settings(_env_file=None).celery_task_default_queue, "openvma-local")
                    self.assertEqual(module.Settings(celery_task_default_queue="explicit-queue").celery_task_default_queue, "explicit-queue")
                with patch.dict(os.environ, {"CELERY_TASK_DEFAULT_QUEUE": "container-queue"}, clear=True):
                    self.assertEqual(module.Settings().celery_task_default_queue, "container-queue")
            finally:
                os.chdir(previous)

    def test_sms_credentials_require_explicit_provider_identity(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(Settings(_env_file=None).has_sms)
            with self.assertRaisesRegex(ValidationError, "SMS_SIGN_NAME"):
                Settings(_env_file=None, sms_access_key_id="fixture-id", sms_access_key_secret="fixture-secret")

    def test_missing_sms_template_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValidationError, "SMS_TEMPLATE_CODE"):
                Settings(_env_file=None, sms_access_key_id="fixture-id", sms_access_key_secret="fixture-secret", sms_sign_name="Example App")
