import time
from typing import Any, Callable, Optional
from contextlib import ContextDecorator
from dataclasses import dataclass, field


class TimerError(Exception):
    """A custom exception used to report errors in use of Timer class."""


@dataclass
class Timer(ContextDecorator):
    """Time your code using a class, context manager, or decorator."""
    
    # Configuration parameters
    name: Optional[str] = None
    message: str = ""
    text: str = "Elapsed time: {:0.4f} s"  # Base format in seconds
    logger: Optional[Callable[[str], None]] = print
    enabled: bool = True
    
    # Internal attributes (instance only)
    _start_time: Optional[int] = field(default=None, init=False, repr=False)
    _elapsed_time_sec: float = field(default=0.0, init=False, repr=False)

    def start(self) -> None:
        """Start a new timer."""
        if not self.enabled:
            return

        if self._start_time is not None:
            raise TimerError("Timer is already running. Use .stop() to stop it.")

        # Usamos perf_counter_ns para una medición de tiempo de alta resolución para benchmarking
        self._start_time = time.perf_counter_ns()

    def stop(self) -> float:
        """Stop the timer and report the elapsed time."""
        if not self.enabled:
            return 0.0

        if self._start_time is None:
            raise TimerError("Timer is not running. Use .start() to start it.")

        # Calculate the elapsed time
        end_time = time.perf_counter_ns()
        elapsed_ns = end_time - self._start_time
        
        # Store and return the time in seconds (standard unit)
        self._elapsed_time_sec = elapsed_ns * 1e-9
        self._start_time = None

        # --- Formatting and Logging Logic ---
        
        msg = f'{self.message} {self.text.format(self._elapsed_time_sec)}'
        
        # Optional format for minutes/hours (only for the log, not the return)
        if self._elapsed_time_sec >= 3600:
            elapsed_time_hour = self._elapsed_time_sec / 3600
            msg = f'{msg} ({elapsed_time_hour:.2f} h).'
        elif self._elapsed_time_sec >= 60:
            elapsed_time_min = self._elapsed_time_sec / 60
            msg = f'{msg} ({elapsed_time_min:.2f} m).'
        else:
            msg = f'{msg}.'

        # Report the elapsed time
        if self.logger:
            self.logger(msg)

        return self._elapsed_time_sec

    # Context Manager Methods
    
    def __enter__(self) -> "Timer":
        """Start a new timer as a context manager."""
        self.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        """Stop the timer as a context manager."""
        if self.enabled:
            self.stop()
            
    # Helper method to get the result outside the context
    @property
    def elapsed_time(self) -> float:
        """Return the measured elapsed time."""
        return self._elapsed_time_sec


# Example usage (optional in the file)
if __name__ == '__main__':
    print("Example usage of Timer as a Context Manager:")
    
    with Timer(message="Simple calculation", name="Test1") as t:
        time.sleep(1.234)
    
    print(f"Measured time (from property): {t.elapsed_time:.4f} s")