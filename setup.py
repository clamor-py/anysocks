# -*- coding: utf-8 -*-

import re
import sys
from pathlib import Path
from setuptools import setup

ROOT = Path(__file__).parent

if sys.version_info < (3, 5):
    raise SystemExit('This requires Python 3.5+')

with open(str(ROOT / 'anysocks' / 'meta.py'), encoding='utf-8') as f:
    VERSION = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', f.read(), re.MULTILINE).group(1)

with open(str(ROOT / 'README.md'), encoding='utf-8') as f:
    README = f.read()

with open(str(ROOT / 'requirements.txt'), encoding='utf-8') as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name='anysocks',
    author='Valentin B.',
    author_email='valentin.be@protonmail.com',
    url='https://github.com/clamor-py/anysocks',
    license='MIT',
    description='WebSocket protocol implementation for anyio',
    long_description=README,
    long_description_content_type='text/markdown',
    project_urls={
        'Documentation': 'https://anysocks.readthedocs.io/en/latest',
        'Source': 'https://github.com/clamor-py/anysocks',
        'Issue tracker': 'https://github.com/clamor-py/anysocks/issues'
    },
    version=VERSION,
    packages=['anysocks'],
    include_package_data=True,
    install_requires=REQUIREMENTS,
    python_requires='>=3.5.0',
    keywords='anysocks websockets websocket client library anyio',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Environment :: Web Environment',
        'Topic :: Communications',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    test_suite='tests.suite'
)
