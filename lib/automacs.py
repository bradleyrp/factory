#!/usr/bin/env python

import os
import ortho

def install_automacs(spot='.',name='automacs',source=None,branch=None):
	"""
	Install a copy of Automacs to a central location
	YAML: 
		_: !!python/object/apply:lib.automacs.install_automacs
		  spot: local
		  name: automacs
	#! note that there was another sync wrapper somewhere in lib
	"""
	print('status installing')
	if not source: source = 'http://github.com/biophyscode/automacs'
	path = os.path.join(spot,name)
	modules_this = {path:source}
	if branch: modules_this['branch'] = branch
	#! no checks for whether it exists or not
	ortho.modules.sync(modules=modules_this,current=True)
	# save the installed location
	ortho.conf['automacs_install'] = path
	ortho.write_config(ortho.conf)
