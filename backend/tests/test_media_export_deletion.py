"""项目媒体、导出下载路径和安全删除辅助逻辑测试。"""

from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi import UploadFile

from app.api.assets import _detect_container, _probe_upload_stream
from app.api.jobs import _export_result_path
from app.tasks import export_tasks, media_tasks
from scripts.backfill_video_previews import needs_preview


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
            "duration_ms": 12500,
            "width": None,
            "height": None,
            "codec": None,
            "audio_codec": "flac",
            "sample_rate": 48000,
            "channels": 2,
            "bitrate": 768000,
        })


class VideoProxyTests(unittest.TestCase):
    def test_backfill_only_selects_video_without_proxy(self):
        self.assertTrue(needs_preview(SimpleNamespace(
            media_type="video",
            preview_path=None,
            file_path="assets/source.mp4",
            deleted_at=None,
        )))
        self.assertFalse(needs_preview(SimpleNamespace(
            media_type="video",
            preview_path="video-previews/asset/preview.mp4",
            file_path="assets/source.mp4",
            deleted_at=None,
        )))
        self.assertTrue(needs_preview(SimpleNamespace(
            media_type="video",
            preview_path="",
            file_path="assets/source.mp4",
            deleted_at=None,
        )))
        self.assertFalse(needs_preview(SimpleNamespace(
            media_type="image",
            preview_path=None,
            file_path="assets/source.png",
            deleted_at=None,
        )))

    @patch.object(media_tasks.subprocess, "run")
    def test_proxy_is_h264_720p_seek_friendly_mp4(self, mock_run):
        def create_output(command, **_kwargs):
            with open(command[-1], "wb") as stream:
                stream.write(b"proxy")
            return SimpleNamespace(returncode=0, stderr="")

        mock_run.side_effect = create_output
        with tempfile.TemporaryDirectory() as directory:
            output_path = f"{directory}/preview.mp4"
            result = media_tasks._transcode_video_proxy("/tmp/source.mov", output_path)

        command = mock_run.call_args.args[0]
        self.assertEqual(result, output_path)
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "yuv420p")
        self.assertEqual(command[command.index("-r") + 1], "30")
        self.assertEqual(command[command.index("-g") + 1], "30")
        self.assertIn("force_original_aspect_ratio=decrease", command[command.index("-vf") + 1])
        self.assertEqual(command[command.index("-movflags") + 1], "+faststart")

    @patch.object(media_tasks.subprocess, "run")
    def test_proxy_transcode_failure_is_reported(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=1, stderr="decoder failed")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "视频代理转码失败"):
                media_tasks._transcode_video_proxy("/tmp/source.mov", f"{directory}/preview.mp4")


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
                "loop": True,
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
        self.assertIn("-stream_loop", command)
        self.assertIn("asetpts=PTS-STARTPTS+3.000000/TB", filter_complex)
        self.assertIn("afade=t=in:st=0:d=1.000000", filter_complex)
        self.assertIn("afade=t=out:st=8.000000:d=2.000000", filter_complex)
        self.assertIn("volume=0.800000", filter_complex)


class ExportWatermarkTests(unittest.TestCase):
    def test_only_free_plan_requires_watermark(self):
        self.assertTrue(export_tasks.requires_export_watermark(0))
        self.assertFalse(export_tasks.requires_export_watermark(1))
        self.assertFalse(export_tasks.requires_export_watermark(2))

    @patch.object(export_tasks, "_run_command")
    @patch.object(export_tasks, "_render_watermark_image")
    def test_watermark_is_burned_at_bottom_right(self, mock_render, mock_run):
        export_tasks._apply_export_watermark(
            "ffmpeg",
            "/tmp/source.mp4",
            "/tmp/output.mp4",
            "/tmp",
            1920,
            1080,
            12.5,
            "/tmp/font.ttf",
            True,
        )
        mock_render.assert_called_once()
        command = mock_run.call_args.args[0]
        filter_complex = command[command.index("-filter_complex") + 1]
        self.assertIn("main_w-overlay_w-30", filter_complex)
        self.assertIn("main_h-overlay_h-30", filter_complex)
        self.assertEqual(command[command.index("-t") + 1], "12.500000")


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
            payload={"format": "mov"},
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


if __name__ == "__main__":
    unittest.main()
