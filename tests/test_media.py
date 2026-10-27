from bot.services.media import (
    MAX_QUALITY_BUTTONS,
    estimate_mp3_size,
    estimate_size,
    extract_qualities,
    is_video_choice,
    video_format_selector,
)

AUDIO_M4A = {
    "format_id": "140",
    "ext": "m4a",
    "vcodec": "none",
    "acodec": "mp4a.40.2",
    "abr": 129,
    "filesize": 2_000_000,
}
AUDIO_OPUS = {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "filesize": 2_500_000}
STORYBOARD = {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none", "height": 90}


def video(height, vcodec="avc1.640028", width=None, tbr=1000, **extra):
    return {
        "vcodec": vcodec,
        "acodec": "none",
        "height": height,
        "width": width or height * 16 // 9,
        "tbr": tbr,
        "ext": "mp4",
        **extra,
    }


def test_groups_by_height_prefers_h264_and_adds_audio_size():
    formats = [
        STORYBOARD,
        AUDIO_M4A,
        AUDIO_OPUS,
        video(1080, vcodec="vp09.00.40.08", tbr=3000, filesize=50_000_000),
        video(1080, tbr=2500, filesize=40_000_000),
        video(720, filesize=20_000_000),
    ]

    qualities = extract_qualities(formats, duration=100)

    assert [q.label for q in qualities] == ["1080p", "720p"]
    # H.264 (40 MB) beats the bigger VP9 file; m4a audio (2 MB) is added on top.
    assert qualities[0].estimated_size == 42_000_000
    assert qualities[1].estimated_size == 22_000_000


def test_combined_format_does_not_add_audio_twice():
    formats = [AUDIO_M4A, {**video(360, filesize=5_000_000), "acodec": "mp4a.40.2"}]

    assert extract_qualities(formats, duration=100)[0].estimated_size == 5_000_000


def test_vertical_video_is_labelled_by_short_side():
    qualities = extract_qualities([video(1920, width=1080, filesize=1)], duration=10)

    assert qualities[0].height == 1920
    assert qualities[0].label == "1080p"


def test_duplicate_labels_and_long_lists_are_trimmed():
    formats = [video(h, filesize=1) for h in (4320, 2160, 1440, 1080, 720, 480, 360, 240, 144)]
    # Two heights that round to the same label: keep only the higher one.
    formats.append(video(1088, width=1080, filesize=1))

    qualities = extract_qualities(formats, duration=10)

    labels = [q.label for q in qualities]
    assert len(labels) == len(set(labels)) == MAX_QUALITY_BUTTONS
    assert labels[0] == "4320p"


def test_unknown_sizes_stay_unknown():
    formats = [video(720, tbr=None)]

    assert extract_qualities(formats, duration=None)[0].estimated_size is None


def test_no_video_formats_means_no_qualities():
    assert extract_qualities([AUDIO_M4A, STORYBOARD, {"vcodec": "avc1"}], duration=10) == ()


def test_estimate_size_prefers_exact_then_approx_then_bitrate():
    assert estimate_size({"filesize": 10, "filesize_approx": 20}, 5) == 10
    assert estimate_size({"filesize_approx": 20, "tbr": 1}, 5) == 20
    assert estimate_size({"tbr": 800}, 10) == 1_000_000
    assert estimate_size({"tbr": 800}, None) is None
    assert estimate_size({}, 10) is None


def test_estimate_mp3_size():
    assert estimate_mp3_size(60) == 1_440_000
    assert estimate_mp3_size(None) is None
    assert estimate_mp3_size(0) is None


def test_offers_hevc_only_resolutions():
    # TikTok: H.264 up to 576p, the 720p version only in H.265.
    formats = [video(1024, width=576, filesize=1), video(1280, vcodec="h265", width=720, filesize=1)]

    assert [q.label for q in extract_qualities(formats, duration=10)] == ["720p", "576p"]


def test_prefers_h264_at_the_same_resolution():
    formats = [video(1024, vcodec="h265", width=576, filesize=2), video(1024, width=576, filesize=1)]

    assert extract_qualities(formats, duration=10)[0].estimated_size == 1


def test_video_format_selector():
    assert video_format_selector(None) == "bv*+ba/b"
    assert video_format_selector(720) == "bv*[height<=?720]+ba/b[height<=?720]"


def test_is_video_choice():
    assert is_video_choice("720")
    assert is_video_choice("best")
    assert not is_video_choice("mp3")
