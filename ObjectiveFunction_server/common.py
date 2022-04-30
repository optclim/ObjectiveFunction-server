__all__ = ['RunType', 'LookupState']

from enum import Enum


class RunType(Enum):
    """the available run types

     * MISFIT: the objective function stores a float value
     * PATH: the objective function stores a path
    """
    MISFIT = 1
    PATH = 2


class LookupState(Enum):
    """the state of the parameter set

     * PROVISIONAL: new entry under consideration
     * NEW: new parameter set
     * CONFIGURING: the model run is being configured
     * CONFIGURED: the model run has been configured
     * ACTIVE: parameter set being computed
     * RUN: the model has run
     * POSTPROCESSING: the model results are being post-processed
     * COMPLETED: completed parameter set
    """
    PROVISIONAL = 1
    NEW = 2
    CONFIGURING = 3
    CONFIGURED = 4
    ACTIVE = 5
    RUN = 6
    POSTPROCESSING = 7
    COMPLETED = 8
