from setuptools import setup
import os,glob,shutil

if not os.path.isdir('ortho'): 
	raise Exception(
		'you must run this from root via `python ortho/setup.py install')
pack_dns = ['build','dist','ortho.egg-info']
dns = [i for i in pack_dns if os.path.isdir(i)]
if any(dns):
	raise Exception(('setup cannot continue with directories %s '
		'because we will clean them afterwards')%dns)

setup(name='ortho',
	version='0.1',
	description='Miscellaneous tools.',
	url='http://github.com/bradleyrp/ortho',
	author='Ryan P. Bradley',
	license='GNU GPLv3',
	packages=['ortho','ortho.queue'],
	package_dir={'':'./'},
	zip_safe=False)

# clean up
for dn in pack_dns: shutil.rmtree(dn)