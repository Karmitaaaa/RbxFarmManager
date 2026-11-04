"""Ejecuta tareas lentas (red, disco) fuera del hilo de la UI."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception as exc:  # se entrega a la UI para mostrarlo
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


_alive: set = set()


def run_async(fn, *args, on_done=None, on_error=None) -> None:
    task = _Task(fn, args)
    _alive.add(task.signals)

    def _finish(handler, value):
        _alive.discard(task.signals)
        if handler:
            handler(value)

    task.signals.done.connect(lambda r: _finish(on_done, r))
    task.signals.failed.connect(lambda e: _finish(on_error, e))
    task.setAutoDelete(True)
    QThreadPool.globalInstance().start(task)
