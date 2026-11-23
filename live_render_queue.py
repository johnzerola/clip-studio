"""Bounded priority queue for captured media waiting to be rendered."""
from itertools import count
from threading import Condition


class LiveRenderQueue:
    def __init__(self, executor, workers, *, pending_limit=6, byte_limit=384 * 1024**2):
        self.executor = executor
        self.workers = workers
        self.pending_limit = pending_limit
        self.byte_limit = byte_limit
        self.pending = []
        self.sequence = count()
        self.active = 0
        self.changed = Condition()

    def offer(self, score, size, run, discard):
        if size > self.byte_limit:
            discard("limite_temporarios")
            return False
        with self.changed:
            item = (score, -next(self.sequence), size, run, discard)
            self.pending.append(item)
            self.pending.sort(reverse=True)
            dropped = []
            while len(self.pending) > self.pending_limit or sum(entry[2] for entry in self.pending) > self.byte_limit:
                dropped.append(self.pending.pop())
            accepted = item in self.pending
            if accepted and self.active < self.workers:
                self.active += 1
                self.executor.submit(self.render_next)
        for entry in dropped:
            entry[4]("prioridade_da_fila")
        return accepted

    def render_next(self):
        with self.changed:
            if not self.pending:
                self.active -= 1
                self.changed.notify_all()
                return
            _, _, _, run, _ = self.pending.pop(0)
        try:
            run()
        finally:
            with self.changed:
                if self.pending:
                    self.executor.submit(self.render_next)
                else:
                    self.active -= 1
                    self.changed.notify_all()

    def wait(self):
        with self.changed:
            self.changed.wait_for(lambda: self.active == 0)
