__all__ = ['Config']

import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dhdtPy-is-not-so-secret'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{basedir}/app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
