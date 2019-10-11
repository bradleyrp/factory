#!/usr/bin/env python

import os
import ortho

def install_automacs(spot,name,source=None):
	"""
	Install a copy of Automacs to a central location
	"""
	print('status installing')
	if not source: source = 'http://github.com/biophyscode/automacs'
	path = os.path.join(spot,name)
	modules_this = {path:source}
	#! no checks for whether it exists or not
	#! branches?
	ortho.modules.sync(modules=modules_this,current=True)
	# save the installed location
	ortho.conf['automacs_install'] = path
	ortho.write_config(ortho.conf)
