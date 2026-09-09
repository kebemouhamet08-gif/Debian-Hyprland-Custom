import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.metadata import (  # noqa: E402
    MetadataError,
    content_signature,
    generate_thumbnail,
    media_type_for_path,
    probe_media,
    scan_fingerprint,
    thumbnail_destination,
)
from mpvpaper_engine.models import MediaType  # noqa: E402


class MetadataTests(unittest.TestCase):
    def test_media_types(self):
        self.assertEqual(media_type_for_path(Path("a.MP4")), MediaType.VIDEO)
        self.assertEqual(media_type_for_path(Path("a.WebP")), MediaType.IMAGE)
        with self.assertRaises(ValueError):
            media_type_for_path(Path("a.txt"))

    def test_ffprobe_uses_one_json_call(self):
        calls = []
        payload = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920,
                 "height": 1080, "avg_frame_rate": "30000/1001"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "12.5", "bit_rate": "4000000"},
        }
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "video.mp4"
            media.touch()

            def runner(command, **_options):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

            result = probe_media(media, runner)
        self.assertEqual(len(calls), 1)
        self.assertIn("-show_streams", calls[0])
        self.assertEqual(result.width, 1920)
        self.assertAlmostEqual(result.fps, 29.97002997)
        self.assertEqual(result.audio_codec, "aac")

    def test_image_has_no_fake_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.touch()
            runner = lambda command, **options: subprocess.CompletedProcess(
                command, 0, json.dumps({
                    "streams": [{"codec_type": "video", "width": 800, "height": 600}],
                    "format": {"duration": "0.04"},
                }), "",
            )
            result = probe_media(image, runner)
        self.assertIsNone(result.duration)
        self.assertEqual(result.media_type, MediaType.IMAGE)

    def test_probe_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "bad.mp4"
            media.touch()
            runner = lambda command, **options: subprocess.CompletedProcess(command, 1, "", "bad")
            with self.assertRaisesRegex(MetadataError, "bad"):
                probe_media(media, runner)

    def test_scan_fingerprint_uses_path_size_and_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "a.mp4"
            media.write_bytes(b"first")
            first = scan_fingerprint(media)
            media.write_bytes(b"second-value")
            self.assertNotEqual(scan_fingerprint(media), first)

    def test_content_signature_matches_duplicate_content(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.mp4"
            second = Path(directory) / "b.mp4"
            payload = b"same" * 400000
            first.write_bytes(payload)
            second.write_bytes(payload)
            self.assertEqual(content_signature(first), content_signature(second))

    def test_content_signature_does_not_read_full_large_file(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "large.mp4"
            media.write_bytes(b"a" * 1_100_000 + b"b" * 1_100_000)
            signature = content_signature(media)
            self.assertTrue(signature.startswith(f"{media.stat().st_size}:"))

    def test_thumbnail_destination_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "a.mp4"
            self.assertEqual(
                thumbnail_destination(media, Path(directory)),
                thumbnail_destination(media, Path(directory)),
            )

    def test_thumbnail_generation_is_lazy_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "a.mp4"
            media.touch()

            def runner(command, **_options):
                Path(command[-1]).write_bytes(b"jpeg")
                return subprocess.CompletedProcess(command, 0, "", "")

            destination = generate_thumbnail(media, Path(directory) / "thumbs", runner)
            self.assertEqual(destination.read_bytes(), b"jpeg")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
