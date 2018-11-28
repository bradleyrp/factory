#!/usr/bin/env python

import os
import ortho

# settings

def get_macdrive():
	"""
	Mount an external drive on a macos system. 
	Use this by running:
		make set_hook deploy_site="\"{'s':'hooks/macdrive.py','f':'get_macdrive'}\""
	Set the mount and source with:
		make set macdrive_paths="\"{'mount':'/Volumes/site-nix','source':'~/worker/site-nix.dmg'}\""
	The purpose is to get a Linux drive with case sensitivity on MacOS which is 
	case insensitive (for some reason).
	"""
	# get mount information from config
	if 'macdrive_paths' not in ortho.conf:
		raise Exception('you need to make an ext4 volume and register it with e.g.: \n'
			'make set macdrive_paths=\"\\\"'
			'{\'mount\':\'/Volumes/site-nix\',\'source\':\'~/worker/site-nix.dmg\'}\\\"\"')
	mount,source = [ortho.conf['macdrive_paths'][k] for k in ['mount','source']]
	mount_abs = os.path.expanduser(os.path.abspath(mount))
	if not os.path.ismount(mount_abs): 
		print('status mounting external drive')
		os.system('hdiutil attach %s'%source)

def flock_installer():
	"""Install flock on OSX."""
	#! standardize this and encode it somehow?
	#! moved this here from inside SimplePackages because it is custom to flock
	#!   however we eventually need to make that more general
	#! note that we also update the configuration here, but SimplePackages
	#!   should do that instead, and handle the return from conf['packages']
	from ortho import conf
	from ortho.packman import github_install,PackageInstance
	site_dn = github_install(
		'https://github.com/discoteq/flock/releases/'
		'download/v0.2.3/flock-0.2.3.tar.xz')
	#! move the remainder of this block to github_install? or a class?
	#! need to hook this up to a package data structure
	if 'packages' not in conf: conf['packages'] = {}
	#! check for overwrite in case of logic error?
	#! currently writing the simplest possible version
	#! we have to save it like this
	conf['packages']['flock'] = {'path':os.path.join(site_dn,'bin','flock')}
	ortho.write_config(conf)
	return PackageInstance(**conf['packages']['flock']).solve
	#! wrap the flock installer in some kind of decorator to make it a package?

def get_flock():
	"""
	Install flock.
	make set_hook flock1="\"{'s':'hooks/macdrive.py','f':'get_flock'}\""
	summary of flow:
		manager.cli.run calls for flock hook and on linux it works fine
		if you are on macos, you can run the set_hook above
		the first time we check for the package and if missing we install
		and then return the path
	possible change: always use this hook, 
		and skip installation if we find flock
	"""
	from ortho.packman import SimplePackages
	return SimplePackages(package='flock',installer=flock_installer).result
