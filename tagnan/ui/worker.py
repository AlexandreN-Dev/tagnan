"""The brain's calls, off the window's thread: a batch or a new course takes minutes, an
explanation up to a minute, a study sheet a minute or two."""

import logging
import threading
from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import QObject, Signal

from tagnan.brain_client import BrainClient, BrainError

logger = logging.getLogger(__name__)


class BrainWorker(QObject):
    batchReady = Signal(object)  # the brain's answer: {"questions": [...], "rejected": [...]}
    batchFailed = Signal(str)
    explained = Signal(int, str)  # question id, text
    explainFailed = Signal(int, str)
    planned = Signal(str, object)  # the words, the brain's answer: {"understood", "course"...}
    planFailed = Signal(str, str)  # the words, the error
    sheetWritten = Signal(int, object)  # question id, a study sheet's words (tagnan.studysheet)
    sheetFailed = Signal(int, str)  # question id, the error
    wordsReady = Signal(object)  # a language's words: {"words": [...], "rejected", "course"}
    wordsFailed = Signal(str)
    levelReady = Signal(str, object)  # the language, questions that place one in it
    levelFailed = Signal(str, str)  # the language, the error
    accountChanged = Signal()

    def __init__(self, client: BrainClient) -> None:
        super().__init__()
        self._client = client
        self.generating = False
        self.offline = False  # development snapshots: no batch, no quota spent
        self.planning = ""  # the words of the course being drawn up
        self.sheeting = False  # a study sheet's words are being written
        self.levelling = ""  # the language one is being placed in
        # Whose Claude login the brain writes with ({"signedIn", "email", "org", "plan"}), None
        # until known. Kept in memory only: never in his database, his settings or his log.
        self.account: dict[str, Any] | None = None
        self._asking_account = False

    def generate(self, request: dict[str, Any]) -> bool:
        """Start writing a batch, unless one is on its way."""
        if self.generating or self.offline:
            return False
        self.generating = True

        def work() -> None:
            try:
                answer = self._client.generate(request)
            except BrainError as error:
                logger.warning("batch failed: %s", error)
                self.generating = False
                self.batchFailed.emit(str(error))
                return
            self.generating = False
            self.batchReady.emit(answer)

        self._start(work)
        return True

    def words(self, request: dict[str, Any]) -> bool:
        """Start writing a language course's words, unless a batch is on its way."""
        if self.generating or self.offline:
            return False
        self.generating = True

        def work() -> None:
            try:
                answer = self._client.words(request)
            except BrainError as error:
                logger.warning("words failed: %s", error)
                self.generating = False
                self.wordsFailed.emit(str(error))
                return
            self.generating = False
            self.wordsReady.emit(answer)

        self._start(work)
        return True

    def level(self, learned: str, speaks: str) -> bool:
        """Start writing the questions that place one in a language, unless some are on
        their way."""
        if self.levelling or self.offline:
            return False
        self.levelling = learned

        def work() -> None:
            try:
                answer = self._client.level({"learned": learned, "speaks": speaks})
            except BrainError as error:
                logger.warning("placement failed: %s", error)
                self.levelling = ""
                self.levelFailed.emit(learned, str(error))
                return
            self.levelling = ""
            self.levelReady.emit(learned, answer)

        self._start(work)
        return True

    def explain(self, question_id: int, request: dict[str, Any]) -> None:
        def work() -> None:
            try:
                text = self._client.explain(request)
            except BrainError as error:
                logger.warning("explanation failed: %s", error)
                self.explainFailed.emit(question_id, str(error))
                return
            self.explained.emit(question_id, text)

        self._start(work)

    def sheet(self, question_id: int, request: dict[str, Any]) -> bool:
        """Start writing a study sheet's words, unless one is on its way."""
        if self.sheeting or self.offline:
            return False
        self.sheeting = True

        def work() -> None:
            try:
                answer = self._client.sheet(request)
            except BrainError as error:
                logger.warning("study sheet failed: %s", error)
                self.sheeting = False
                self.sheetFailed.emit(question_id, str(error))
                return
            self.sheeting = False
            self.sheetWritten.emit(question_id, answer)

        self._start(work)
        return True

    def plan(
        self,
        words: str,
        language: Mapping[str, Any] | None = None,
        course: Mapping[str, Any] | None = None,
    ) -> bool:
        """Start drawing up a course, unless one is on its way. With `language` ({"learned",
        "speaks", "level"}), a language course's chapters; with `course` too, it a level up."""
        if self.planning:
            return False
        self.planning = words

        def work() -> None:
            try:
                answer = self._client.plan(words, language, course)
            except BrainError as error:
                logger.warning("course failed: %s", error)
                self.planning = ""
                self.planFailed.emit(words, str(error))
                return
            self.planning = ""
            self.planned.emit(words, answer)

        self._start(work)
        return True

    def look_up_account(self) -> None:
        """Ask the brain whose Claude login it writes with, unless it is being asked."""
        if self.offline or self._asking_account:
            return
        self._asking_account = True

        def work() -> None:
            found: dict[str, Any] | None
            try:
                found = self._client.account()
            except BrainError as error:
                logger.warning("account not known: %s", error)
                found = None  # rather none than one that may no longer be true
            self._asking_account = False
            if found != self.account:
                self.account = found
                self.accountChanged.emit()

        self._start(work)

    @staticmethod
    def _start(work: Callable[[], None]) -> None:
        threading.Thread(target=work, daemon=True).start()
