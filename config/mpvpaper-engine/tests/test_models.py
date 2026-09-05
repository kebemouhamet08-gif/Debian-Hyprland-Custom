from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.models import (  # noqa: E402
    AnimatedPreview,
    ColorProfile,
    DownloadJob,
    DownloadState,
    HistoryEntry,
    MediaType,
    OutputMode,
    OutputProfile,
    PerformanceMode,
    PerformanceProfile,
    PlaybackState,
    PlaybackStatus,
    Playlist,
    PlaylistItem,
    PlaylistMode,
    Wallpaper,
)


class ModelTests(unittest.TestCase):
    def test_enums_have_stable_string_values(self):
        self.assertEqual(MediaType.VIDEO.value, "video")
        self.assertEqual(PlaybackStatus.PAUSED.value, "paused")
        self.assertEqual(OutputMode.SYNC.value, "sync")
        self.assertEqual(PerformanceMode.BALANCED.value, "balanced")
        self.assertEqual(PlaylistMode.SMART.value, "smart")
        self.assertEqual(DownloadState.CANCELLED.value, "cancelled")

    def test_wallpaper_and_related_models_construct(self):
        now = datetime.now(timezone.utc)
        wallpaper = Wallpaper(1, Path("/library/night.mp4"), "Night", MediaType.VIDEO)
        playlist = Playlist(2, "Night", PlaylistMode.SMART)
        item = PlaylistItem(playlist.id, wallpaper.id, 0)
        history = HistoryEntry(3, wallpaper.id, "eDP-1", now)
        job = DownloadJob("job-1", "web", "https://example.test/night.mp4")

        self.assertEqual(item.weight, 1.0)
        self.assertEqual(history.reason, "manual")
        self.assertEqual(job.state, DownloadState.QUEUED)
        self.assertEqual(asdict(wallpaper)["title"], "Night")

    def test_color_profile_defaults_match_legacy_engine(self):
        profile = ColorProfile()

        self.assertEqual(profile.brightness, 0)
        self.assertEqual(profile.contrast, 0)
        self.assertEqual(profile.gamma, 0)
        self.assertEqual(profile.saturation, 0)
        self.assertEqual(profile.hue, 0)
        self.assertEqual(profile.temperature, 6500)
        self.assertEqual(profile.red_balance, 0)
        self.assertEqual(profile.green_balance, 0)
        self.assertEqual(profile.blue_balance, 0)

    def test_output_playback_and_performance_defaults(self):
        output = OutputProfile("eDP-1")
        state = PlaybackState("eDP-1")
        performance = PerformanceProfile()

        self.assertEqual(output.mode, OutputMode.INDEPENDENT)
        self.assertEqual(output.performance_profile, PerformanceMode.AUTO)
        self.assertEqual(state.status, PlaybackStatus.STOPPED)
        self.assertEqual(performance.hwdec, "auto-safe")
        self.assertEqual(performance.animated_preview, AnimatedPreview.SELECTION)
        self.assertEqual(performance.theme_analysis_frames, 4)


if __name__ == "__main__":
    unittest.main()
