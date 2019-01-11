import traceback
from PyQt5 import QtCore


class Worker(QtCore.QObject):
    """
    Implements a worker object on which functions can be executed for multi-threading within Qt.
    The worker must be moved to a QThread via the QObject.moveToThread() method.
    """

    finished = QtCore.pyqtSignal()
    exceptionSignal = QtCore.pyqtSignal(Exception, str)

    def __init__(self, func, *args, **kwargs):
        super(Worker, self).__init__()

        # Main function which will be executed on this thread
        self.func = func
        # Arguments of main function
        self.args = args
        # Keyword arguments of main function
        self.kwargs = kwargs

    def work(self):
        """
        Runs the function func with given arguments args and keyword arguments kwargs.
        If errors or exceptions occur, a signal sends the exception to main thread.
        """

        try:
            if self.args and self.kwargs:
                self.func(*self.args, **self.kwargs)
            elif self.args:
                self.func(*self.args)
            elif self.kwargs:
                self.func(**self.kwargs)
            else:
                self.func()

            self.finished.emit()

        except Exception as e:
            # Format traceback and send
            trc_bck = traceback.format_exc()
            # Emit exception signal
            self.exceptionSignal.emit(e, trc_bck)