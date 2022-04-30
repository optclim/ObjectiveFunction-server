__all__ = ['RunType']

from enum import Enum


class RunType(Enum):
    """the available run types

     * MISFIT: the objective function stores a float value
     * PATH: the objective function stores a path
    """
    MISFIT = 1
    PATH = 2
