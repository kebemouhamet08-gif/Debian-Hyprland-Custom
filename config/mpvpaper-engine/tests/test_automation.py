from pathlib import Path
import sys
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.automation import (  # noqa: E402
    AutomationAction,
    AutomationEvent,
    AutomationReason,
    SmartPauseController,
    dpms_event,
    logind_event,
    parse_hyprland_event,
    upower_event,
)
from mpvpaper_engine.models import PlaybackState  # noqa: E402


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.playback = mock.Mock()
        self.playback.get_state.return_value = PlaybackState("DP-1", speed=1.25)
        self.smart = SmartPauseController(self.playback)

    def event(self, reason, active):
        return AutomationEvent(reason, active)

    def test_fullscreen_pauses_and_leaving_resumes(self):
        self.smart.handle("DP-1", self.event(AutomationReason.FULLSCREEN, True))
        self.smart.handle("DP-1", self.event(AutomationReason.FULLSCREEN, False))
        self.playback.pause.assert_called_once_with("DP-1")
        self.playback.resume.assert_called_once_with("DP-1")

    def test_reasons_stack_before_resume(self):
        self.smart.handle("DP-1", self.event(AutomationReason.FULLSCREEN, True))
        self.smart.handle("DP-1", self.event(AutomationReason.LOCK, True))
        self.smart.handle("DP-1", self.event(AutomationReason.LOCK, False))
        self.playback.resume.assert_not_called()
        self.smart.handle("DP-1", self.event(AutomationReason.FULLSCREEN, False))
        self.playback.resume.assert_called_once_with("DP-1")

    def test_duplicate_event_is_idempotent(self):
        event = self.event(AutomationReason.LOCK, True)
        self.smart.handle("DP-1", event)
        self.smart.handle("DP-1", event)
        self.playback.pause.assert_called_once()

    def test_battery_reduces_and_restores_original_speed(self):
        self.smart.handle("DP-1", self.event(AutomationReason.BATTERY, True))
        self.smart.handle("DP-1", self.event(AutomationReason.BATTERY, False))
        self.playback.set_speed.assert_has_calls([
            mock.call("DP-1", 0.5), mock.call("DP-1", 1.25),
        ])

    def test_reduce_reasons_stack(self):
        self.smart.handle("DP-1", self.event(AutomationReason.BATTERY, True))
        self.smart.handle("DP-1", self.event(AutomationReason.POWER_SAVER, True))
        self.smart.handle("DP-1", self.event(AutomationReason.BATTERY, False))
        self.assertEqual(self.playback.set_speed.call_count, 1)
        self.smart.handle("DP-1", self.event(AutomationReason.POWER_SAVER, False))
        self.assertEqual(self.playback.set_speed.call_count, 2)

    def test_stop_policy_never_auto_restores(self):
        smart = SmartPauseController(self.playback, policy={
            AutomationReason.LOCK: AutomationAction.STOP,
        })
        smart.handle("DP-1", self.event(AutomationReason.LOCK, True))
        smart.handle("DP-1", self.event(AutomationReason.LOCK, False))
        self.playback.stop.assert_called_once_with("DP-1")
        self.playback.resume.assert_not_called()

    def test_continue_policy_has_no_playback_action(self):
        smart = SmartPauseController(self.playback, policy={
            AutomationReason.FULLSCREEN: AutomationAction.CONTINUE,
        })
        smart.handle("DP-1", self.event(AutomationReason.FULLSCREEN, True))
        self.playback.pause.assert_not_called()

    def test_hyprland_events_are_parsed(self):
        self.assertEqual(
            parse_hyprland_event("fullscreen>>1"),
            self.event(AutomationReason.FULLSCREEN, True),
        )
        self.assertEqual(
            parse_hyprland_event("fullscreen>>0"),
            self.event(AutomationReason.FULLSCREEN, False),
        )
        self.assertIsNone(parse_hyprland_event("workspace>>2"))

    def test_logind_and_dpms_events(self):
        self.assertEqual(logind_event(locked=True), self.event(AutomationReason.LOCK, True))
        self.assertEqual(
            logind_event(preparing_for_sleep=True),
            self.event(AutomationReason.SUSPEND, True),
        )
        self.assertEqual(dpms_event(False), self.event(AutomationReason.DPMS, True))

    def test_upower_emits_battery_and_power_profile(self):
        events = upower_event(on_battery=True, power_saver=True)
        self.assertEqual(events, [
            self.event(AutomationReason.BATTERY, True),
            self.event(AutomationReason.POWER_SAVER, True),
        ])

    def test_invalid_dpms_state_is_rejected(self):
        with self.assertRaises(ValueError):
            dpms_event("off")


if __name__ == "__main__":
    unittest.main()
