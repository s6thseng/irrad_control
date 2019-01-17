import traceback
from PyQt5 import QtCore


class WorkerSignals(QtCore.QObject):
    
    finished = QtCore.pyqtSignal()
    exceptionSignal = QtCore.pyqtSignal(Exception, str)

class Worker(QtCore.QRunnable):
    """
    Implements a worker on which functions can be executed for multi-threading within Qt.
    The worker is an instance of QRunnable, which can be started and handled automatically by Qt and its QThreadPool.
    """

    def __init__(self, func, *args, **kwargs):
        super(Worker, self).__init__()

        # Main function which will be executed on this thread
        self.func = func
        # Arguments of main function
        self.args = args
        # Keyword arguments of main function
        self.kwargs = kwargs
        
        # Needs to be done this way since QRunnable cannot emit signals; QObject needed
        self.signals = WorkerSignals()
    
    @QtCore.pyqtSlot()
    def run(self):
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

        except Exception as e:
            # Format traceback and send
            trc_bck = traceback.format_exc()
            # Emit exception signal
            self.signals.exceptionSignal.emit(e, trc_bck)
            
        finally:
            self.signals.finished.emit()