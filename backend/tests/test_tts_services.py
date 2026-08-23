from app.services.tts.normalization import (
    dashscope_billable_characters,
    make_request_hash,
    normalize_tts_text,
    validate_tts_selection,
)
from app.services.tts.segmenter import segment_text
from app.services.tts.planning import build_voice_plans
from app.services.tts.dashscope import normalize_dashscope_audio_url


class StubShot:
    def __init__(self, identity: str, text: str, overridden: bool = False):
        self.id = identity
        self.duration_ms = 2000
        self.subtitle_text = text
        self.subtitle_overridden = overridden


class StubScene:
    id = "scene-1"
    narration_text = "整段场景旁白。"

    def __init__(self):
        self.shots = [
            StubShot("shot-1", self.narration_text),
            StubShot("shot-2", "手工补充台词。", True),
            StubShot("shot-3", self.narration_text),
            StubShot("shot-4", "结尾手工台词。", True),
        ]


class StubProject:
    def __init__(self):
        self.script = type("Script", (), {"units": [StubScene()]})()


def test_normalize_and_bill_chinese_characters():
    assert normalize_tts_text("  你好   OpenVMA  ") == "你好 OpenVMA"
    assert dashscope_billable_characters("你好A") == 5


def test_segmenter_keeps_short_sentences_together_and_splits_long_text():
    assert segment_text("你好。世界！", minimum=8, maximum=20) == ["你好。世界！"]
    result = segment_text("这是第一段很长的说明，需要在逗号附近自然切开，同时不要破坏主要语义。", minimum=4, maximum=12)
    assert len(result) >= 2
    assert "".join(result) == "这是第一段很长的说明，需要在逗号附近自然切开，同时不要破坏主要语义。"


def test_request_hash_changes_with_voice_or_instruction():
    base = dict(provider="dashscope", model="qwen3-tts-flash", text="你好", language="Chinese", emotion="")
    first = make_request_hash(**base, voice="Cherry", instruction="自然")
    assert first == make_request_hash(**base, voice="Cherry", instruction="自然")
    assert first != make_request_hash(**base, voice="Ethan", instruction="自然")
    assert first != make_request_hash(**base, voice="Cherry", instruction="严肃")


def test_effective_subtitles_use_exact_shot_windows_without_estimated_retiming():
    plans = build_voice_plans(StubProject(), {"scene-1"}, "effective_subtitles")
    joined = "".join(plan["text"] for plan in plans)
    # 同一句字幕在不连续的时间窗重新出现时是两个 cue；它不会跨过中间的
    # 手工字幕，也不会在 TTS 阶段按字数重新分配起点。
    assert joined.count("整段场景旁白。") == 2
    assert joined.count("手工补充台词。") == 1
    assert joined.count("结尾手工台词。") == 1
    assert [(plan["start_ms"], plan["end_ms"]) for plan in plans] == [
        (0, 2000), (2000, 4000), (4000, 6000), (6000, 8000),
    ]
    assert all(plan["speech_budget_ms"] == 1900 for plan in plans)
    ending = next(plan for plan in plans if "结尾手工台词" in plan["text"])
    assert ending["start_ms"] == 6000


def test_adjacent_identical_subtitles_are_one_cue_with_combined_window():
    scene = StubScene()
    scene.shots = [
        StubShot("shot-1", "同一句字幕。", True),
        StubShot("shot-2", "同一句字幕。", True),
    ]
    project = type("Project", (), {"script": type("Script", (), {"units": [scene]})()})()
    plans = build_voice_plans(project, {"scene-1"}, "effective_subtitles")
    assert len(plans) == 1
    assert plans[0]["start_ms"] == 0
    assert plans[0]["end_ms"] == 4000
    assert plans[0]["start_shot_id"] == "shot-1"
    assert plans[0]["end_shot_id"] == "shot-2"


def test_model_and_voice_compatibility_guard():
    validate_tts_selection("qwen-audio-3.0-tts-flash", "longanfengyue")
    validate_tts_selection("qwen3-tts-flash", "Cherry")
    try:
        validate_tts_selection("qwen-audio-3.0-tts-flash", "Cherry")
    except ValueError:
        pass
    else:
        raise AssertionError("Qwen3 voice must not be accepted by Qwen-Audio")
    try:
        validate_tts_selection("qwen-unknown-tts", "Cherry")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported models must be rejected")


def test_dashscope_result_url_is_upgraded_without_weakening_other_hosts():
    official = "http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/result.wav?token=abc"
    assert normalize_dashscope_audio_url(official) == (
        "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/result.wav?token=abc"
    )
    assert normalize_dashscope_audio_url("http://example.com/result.wav") == (
        "http://example.com/result.wav"
    )
    assert normalize_dashscope_audio_url(
        "http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com:80/result.wav"
    ).startswith("http://")
