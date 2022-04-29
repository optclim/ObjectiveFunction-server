from .application import app, db  # noqa F401
from .routes import *  # noqa F401 F403
from .models import *  # noqa F401 F403
import logging


if __name__ != '__main__':
    # get gunicorn logger when the app is not run stand alone
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
