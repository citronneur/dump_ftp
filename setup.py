#!/usr/bin/env python

import setuptools
from distutils.core import setup

setup(name='dump_ftp',
	version='1.0.0',
	description='Dump FTP file tree into local environment',
	author='Sylvain Peyrefitte',
	author_email='citronneur@gmail.com',
	url='https://github.com/citronneur/dump_ftp',
	scripts = [
			'dump_ftp.py', 
		],
)
