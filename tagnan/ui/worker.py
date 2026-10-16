"""The brain's calls, off the window's thread: a batch or a new course takes minutes, an
explanation up to a minute."""

import logging
import threading
from collections.abc import Callable
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

    def __init__(self, client: BrainClient) -> None:
        super().__init__()
        self._client = client
        self.generating = False
        self.planning = ""  # the words of the course being drawn up

    def generate(self, request: dict[str, Any]) -> bool:
        """Start writing a batch, unless one is on its way."""
        if self.generating:
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

    def plan(self, words: str) -> bool:
        """Start drawing up a course, unless one is on its way."""
        if self.planning:
            return False
        self.planning = words

        def work() -> None:
            try:
                answer = self._client.plan(words)
            except BrainError as error:
                logger.warning("course failed: %s", error)
                self.planning = ""
                self.planFailed.emit(words, str(error))
                return
            self.planning = ""
            self.planned.emit(words, answer)

        self._start(work)
        return True

    @staticmethod
    def _start(work: Callable[[], None]) -> None:
        threading.Thread(target=work, daemon=True).start()
