import atexit
import logging
import os
import sys
import time
from ctypes import CDLL
from threading import Lock
from typing import Iterable, Callable

import pync
import rumps
from rumps import MenuItem

import keyboard
from keyboard import KeyboardEvent
from keyboard_utils import PARTH_QWERTY
from rules.events_eligibility_rule import EventsEligibilityRule
from rules.rules import NumEventsNotReleased, EventsWithinNumSeconds, CheckAllAdjacent


APP_NAME = "Pawse"
APP_NAME_PAST_TENSE = f"{APP_NAME}d"


logging.basicConfig()
logging.getLogger().setLevel(level=logging.DEBUG)


CAT_PAW_DETECTION_RULES = (
    EventsWithinNumSeconds(num_seconds=0.05),
    NumEventsNotReleased(num_events=3),
    CheckAllAdjacent(distance=3, keyboard_fmt=PARTH_QWERTY),
)


START = "Start"
STOP = "Stop"


class StatusBarApp(rumps.App):
    """Defines how the status bar app works."""

    def __init__(self, *args, rules: Iterable[EventsEligibilityRule], detected_callback: Callable[[], None], **kwargs):
        """Initializes"""
        super().__init__(*args, **kwargs)
        self.rules = rules
        self.presses: list[KeyboardEvent] = []
        self.presses_lock = Lock()
        self.kill_paw_detection: Callable = None
        self.detected_callback = detected_callback
        self.start_detection()

    @rumps.clicked(STOP)
    def start_stop(self, sender: MenuItem) -> None:
        logging.info(f"Performing {sender.title}")
        if sender.title == START:
            self.start_detection()
        else:
            self.stop_detection()
        sender.title = START if sender.title == STOP else STOP

    def detect_presses(self, rules: Iterable[EventsEligibilityRule], success_callback: Callable[[], None]) -> Callable[[KeyboardEvent], None]:
        """Detect x presses within x seconds.

        Args:
            rules: Rules to check if the last num_presses events match
            success_callback: Calls this if all rules pass.
        """

        def _detect_presses(event: KeyboardEvent) -> None:
            with self.presses_lock:
                self.presses.append(event)

                for rule in rules:
                    passed, self.presses = rule.check(events=self.presses)
                    if not passed:
                        return

            # Didn't early return means we detected an event.
            logging.info("Calling success.")
            logging.debug(f"Presses: {self.presses} made it through.")
            success_callback()

        return _detect_presses

    def start_detection(self) -> None:
        """Starts paws detection"""
        assert not self.kill_paw_detection, f"Already started!"
        logging.info("Starting detection.")
        self.kill_paw_detection = keyboard.on_press(
            callback=self.detect_presses(
                rules=self.rules,
                success_callback=self.detected_callback,
            ),
        )
        atexit.register(self.kill_paw_detection)
        time.sleep(1)
        logging.info("Started detection.")

    def stop_detection(self) -> None:
        assert self.kill_paw_detection, f"You must start detection before we can stop detection."
        logging.info("Stopping detection.")
        self.kill_paw_detection()
        atexit.unregister(self.kill_paw_detection)
        self.kill_paw_detection = None
        logging.info("Stopped detection.")


LOGIN_DLL = CDLL('/System/Library/PrivateFrameworks/login.framework/Versions/Current/login')


def lock_mac(icon_path: str) -> Callable[[], None]:
    """Locks macOS

    Args:
        icon_path: Added as part of the content. Sadly terminal-notifier (what pync uses internally) no
            longer supports custom notification images.
    """
    def _lock_mac() -> None:
        LOGIN_DLL.SACLockScreenImmediate()
        # Sleep so notification appears on lock screen.
        # May want to move the sleep + notification to another thread, so we don't lock up the main thread.
        # However, this doesn't seem to cause problems yet.
        time.sleep(0.4)
        pync.notify(title=f"{APP_NAME_PAST_TENSE}", message=f"{APP_NAME} detected kitty paws!", contentImage=icon_path, appImage=icon_path)

    return _lock_mac


ICON_PATH = "images/cat_scream_emoji.png"


if __name__ == "__main__":
    program_path = os.path.abspath(os.path.dirname(sys.argv[0]))
    icon_path = os.path.join(program_path, ICON_PATH)
    logging.debug(f"Detected path for status bar icon: {icon_path}")
    StatusBarApp(name=APP_NAME, icon=icon_path, rules=CAT_PAW_DETECTION_RULES, detected_callback=lock_mac(icon_path=icon_path)).run()
