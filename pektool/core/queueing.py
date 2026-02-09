from __future__ import annotations

import queue


def create_queue(maxsize: int) -> queue.Queue:
    return queue.Queue(maxsize=maxsize)