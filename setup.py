from setuptools import setup, find_packages
from sphinx.setup_command import BuildDoc

name = 'ObjectiveFunction-server'
version = '0.2'
release = '0.2.0'
author = 'Magnus Hagdorn'

setup(
    name=name,
    packages=find_packages(),
    version=release,
    include_package_data=True,
    install_requires=[
        "sqlalchemy",
        "flask>=1.0",
        "flask_sqlalchemy",
        "itsdangerous",
        "passlib",
        "flask-httpauth",
        "pandas",
    ],
    cmdclass={'build_sphinx': BuildDoc},
    command_options={
        'build_sphinx': {
            'project': ('setup.py', name),
            'version': ('setup.py', version),
            'release': ('setup.py', release),
            'copyright': ('setup.py', author),
            'source_dir': ('setup.py', 'docs')}},
    setup_requires=['sphinx'],
    extras_require={
        'docs': [
            'sphinx<4.0',
            'sphinx_rtd_theme',
            'sphinxcontrib.httpdomain',
        ],
        'lint': [
            'flake8>=3.5.0',
        ],
        'testing': [
            'pytest',
            'flask-testing',
        ],
    },
    entry_points={
        'console_scripts': [
            'objfun-server=ObjectiveFunction_server.app:main',
            'objfun-admin=ObjectiveFunction_server.manage:main',
        ],
    },
    author=author,
    description=("database backend for ObjectiveFunction"
                 " optimisation framework"),
)
