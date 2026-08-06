"""项目媒体、导出下载路径和安全删除辅助逻辑测试。"""

from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi import UploadFile

from app.api.assets import _detect_container, _probe_upload_stream
from app.api.jobs import _export_result_path
from app.services.deletion import _timeline_asset_references
from app.services.project_media import generated_kind
from app.services.timeline_validation import validate_timeline_layout
from app.tasks import export_tasks


class ProjectMediaTests(unittest.TestCase):
    def test_generated_kind_distinguishes_image_video_and_effect(self):
        self.assertEqual(generated_kind("generated/images/a.png", "image"), "ai_image")
        self.assertEqual(generated_kind("generated/videos/a.mp4", "video"), "ai_video")
        self.assertEqual(generated_kind("generated/effects/a.mp4", "video"), "ai_effect_video")

    def test_manual_generated_media_is_valid_without_asset(self):
        issues = validate_timeline_layout(
            [
                {
                    "id": "clip-1",
                    "name": "素材箱 AI 视频",
                    "track": "video",
                    "start": 0,
                    "duration": 5,
                    "origin": "manual_generated",
                    "generated_media_path": "generated/videos/a.mp4",
                    "generated_media_type": "video",
                }
            ],
            {},
        )
        self.assertEqual(issues, [])

    def test_manual_generated_media_requires_storage_path(self):
        issues = validate_timeline_layout(
            [
                {
                    "name": "缺失文件",
                    "track": "video",
                    "start": 0,
                    "duration": 5,
                    "origin": "manual_generated",
                    "generated_media_type": "video",
                }
            ],
            {},
        )
        self.assertEqual(issues, ["AI 生成片段「缺失文件」缺少可用媒体"])

    def test_audio_asset_is_rejected_on_video_track(self):
        asset = SimpleNamespace(id="audio-1", duration=12, media_type="audio", has_audio=True)
        issues = validate_timeline_layout(
            [{
                "name": "背景音乐",
                "track": "video",
                "asset_id": "audio-1",
                "start": 0,
                "duration": 5,
                "source_start": 0,
            }],
            {"audio-1": asset},
        )
        self.assertIn("视频片段「背景音乐」引用的是音频素材", issues)

    def test_silent_video_is_rejected_on_audio_track(self):
        asset = SimpleNamespace(id="video-1", duration=12, media_type="video", has_audio=False)
        issues = validate_timeline_layout(
            [{
                "name": "无声素材",
                "track": "audio",
                "asset_id": "video-1",
                "start": 0,
                "duration": 5,
                "source_start": 0,
            }],
            {"video-1": asset},
        )
        self.assertIn("音频片段「无声素材」引用的素材没有可用音轨", issues)


class AudioUploadDetectionTests(unittest.TestCase):
    def test_recognizes_supported_audio_headers(self):
        self.assertEqual(_detect_container(b"RIFF\x00\x00\x00\x00WAVEfmt "), "wav")
        self.assertEqual(_detect_container(b"fLaC\x00\x00\x00\x22"), "flac")
        self.assertEqual(_detect_container(b"OggS\x00\x02"), "ogg")
        self.assertEqual(_detect_container(b"ID3\x04\x00"), "mp3")
        self.assertEqual(_detect_container(bytes([0xFF, 0xF1, 0x50, 0x80])), "aac")

    def test_aac_adts_is_not_misclassified_as_mp3(self):
        self.assertEqual(_detect_container(bytes([0xFF, 0xF9, 0x4C, 0x80])), "aac")

    @patch("app.api.assets.subprocess.run")
    def test_probe_accepts_audio_only_media(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps({
                "format": {"duration": "12.5"},
                "streams": [{
                    "codec_type": "audio",
                    "codec_name": "flac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "bit_rate": "768000",
                }],
            }),
        )
        with tempfile.TemporaryFile() as stream:
            stream.write(b"fLaC\x00\x00\x00\x22")
            stream.seek(0)
            result = _probe_upload_stream(UploadFile(file=stream, filename="music.flac"))

        self.assertEqual(result["openvma"], {
            "media_type": "audio",
            "has_audio": True,
            "duration": 12.5,
            "audio_codec": "flac",
            "sample_rate": 48000,
            "channels": 2,
            "bitrate": 768000,
        })


class AudioExportFilterTests(unittest.TestCase):
    @patch.object(export_tasks, "_run_command")
    @patch.object(export_tasks, "_has_audio", return_value=True)
    def test_video_audio_filters_include_mute_denoise_and_fades(self, _mock_has_audio, mock_run):
        export_tasks._render_video_segment(
            "ffmpeg",
            "ffprobe",
            {
                "name": "测试视频",
                "source_path": "/tmp/source.mp4",
                "duration": 8,
                "source_start": 0,
                "transform": {},
                "adjust": {},
                "transition": {"type": "none", "duration": 0.5},
                "audio": {
                    "volume": 160,
                    "muted": True,
                    "denoise": True,
                    "fade_in": 1.5,
                    "fade_out": 2,
                },
            },
            "/tmp/out.mp4",
            1920,
            1080,
        )
        command = mock_run.call_args.args[0]
        filter_complex = command[command.index("-filter_complex") + 1]
        self.assertIn("afftdn=nf=-25", filter_complex)
        self.assertIn("afade=t=in:st=0:d=1.500000", filter_complex)
        self.assertIn("afade=t=out:st=6.000000:d=2.000000", filter_complex)
        self.assertIn("volume=0.000000", filter_complex)

    @patch.object(export_tasks, "_run_command")
    @patch.object(export_tasks, "_has_audio", return_value=True)
    def test_independent_audio_track_filters_are_mixed(self, _mock_has_audio, mock_run):
        export_tasks._mix_audio_tracks(
            "ffmpeg",
            "ffprobe",
            "/tmp/rendered.mp4",
            [{
                "name": "BGM",
                "source_path": "/tmp/music.wav",
                "source_start": 2,
                "start": 3,
                "duration": 10,
                "audio": {
                    "volume": 80,
                    "muted": False,
                    "denoise": False,
                    "fade_in": 1,
                    "fade_out": 2,
                },
            }],
            "/tmp/mixed.mp4",
            20,
        )
        command = mock_run.call_args.args[0]
        filter_complex = command[command.index("-filter_complex") + 1]
        self.assertIn("asetpts=PTS-STARTPTS+3.000000/TB", filter_complex)
        self.assertIn("afade=t=in:st=0:d=1.000000", filter_complex)
        self.assertIn("afade=t=out:st=8.000000:d=2.000000", filter_complex)
        self.assertIn("volume=0.800000", filter_complex)


class ExportResultPathTests(unittest.TestCase):
    def test_prefers_durable_result_path(self):
        job = SimpleNamespace(
            result_path="exports/project/job.mov",
            type="导出",
            status="SUCCEEDED",
            payload={"format": "mp4"},
            project_id="project",
            id="job",
        )
        self.assertEqual(_export_result_path(job), "exports/project/job.mov")

    def test_backfills_legacy_successful_export_path(self):
        job = SimpleNamespace(
            result_path=None,
            type="导出",
            status="SUCCEEDED",
            payload={"format": "prores"},
            project_id="project-1",
            id="job-1",
        )
        self.assertEqual(_export_result_path(job), "exports/project-1/job-1.mov")

    def test_incomplete_export_has_no_download_path(self):
        job = SimpleNamespace(
            result_path=None,
            type="导出",
            status="RUNNING",
            payload={"format": "mp4"},
            project_id="project-1",
            id="job-1",
        )
        self.assertIsNone(_export_result_path(job))


class DeletionImpactHelpersTests(unittest.TestCase):
    def test_counts_only_matching_timeline_asset_references(self):
        timeline = [
            {"asset_id": "asset-1"},
            {"asset_id": "asset-2"},
            {"asset_id": "asset-1"},
            {"generated_media_path": "generated/images/a.png"},
        ]
        self.assertEqual(_timeline_asset_references(timeline, "asset-1"), 2)
        self.assertEqual(_timeline_asset_references(timeline, "asset-3"), 0)


if __name__ == "__main__":
    unittest.main()
