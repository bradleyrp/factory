#!/usr/bin/env python

#! manually pick up the overloaded print
from __future__ import print_function
import os,copy,re,sys,glob,pprint
import ortho
import multiprocessing
import tempfile
import shutil
# several functions below use yaml 
#! we typically use the requirement function to load yaml in each function
try:
	import yaml
	from ortho.yaml_mods import YAMLObjectInit
	# loading yaml_mods adds extra tags and constructors
	from ortho.yaml_mods import yaml_tag_strcat_custom,yaml_tag_merge_list
	# chain feature for handling dependencies
	yaml.add_constructor('!chain',yaml_tag_strcat_custom(" ^"))
	# additional shorthand
	yaml.add_constructor('!str',yaml_tag_strcat_custom(" "))
	yaml.add_constructor('!strflush',yaml_tag_strcat_custom(""))
	def yaml_tag_loop_packages(self,node):
		this = self.construct_mapping(node,deep=True)
		if set(this.keys())!=set(['base','loop']):
			raise Exception('invalid format: %s'%str(this))
		return ['%s %s'%(i,this['base']) for i in this['loop']]
	yaml.add_constructor('!loopcat',yaml_tag_loop_packages)
	def yaml_tag_looper(self,node):
		"""
		Add a value to many keys.
		"""
		# we automatically squence these because we often have to 
		#   combine longer lists and we failed to use this under
		#   a !merge_lists tag. probably need a yield. handling
		#   lists here instead
		outer = self.construct_sequence(node,deep=True)
		result = {}
		for this in outer:
			if this.keys()>{'item','keys','suffix'}:
				raise Exception('invalid format: %s'%str(this))
			suffix = this.get('suffix','')
			if suffix: suffix = ' '+suffix
			up = dict([(i,this['item']+suffix) for i in this['keys']])
			result.update(**up)
		return result
	# generic !merge_lists tag is highly useful
	yaml.add_constructor('!looper',yaml_tag_looper)
except Exception as e: 
	#! yaml error here if you raise
	#! hence this is loaded twice. consider fixing? or explicate
	print(e)
	pass
from ortho import Handler
from ortho import CacheChange
from ortho import path_resolver
from ortho import catalog
from ortho import delveset,delve
from ortho import requires_python_check
from ortho import bash
from ortho.yaml_run import yaml_do_select
from ortho.handler import incoming_handlers

"""
NOTES on path configuration and order of precedence

The yaml "spec" sent to spack_tree (possibly via spack_hpc_deploy) contains
two settings for paths: `spot` and `spot_envs`. The `SpackSeq.seq_envs` 
method sends these keys to `config_or_make` which gets these keys from the
`config.json`. If they are not there yet or the directories do not yet exist, 
it builds the targert by either cloning spack to `spot` or making the parent 
`spot_envs` directory. When it builds, it writes the location to `config.json`
for next time. This means that after running `spack_tree` if you change the
spot, the change will be ignored unless you remove it from the `config.json`
because we do not have a feature that automatically moves things. The 
`config_or_make` function provides warnings about this. Note that the keys in
the yaml file (`spot` and `spot_envs`) are different than those in the config
(`spack` and `spack_envs`) for clarity in the yaml. Defaults are coded in
this file, but also provided for the yaml when it is loaded. 
"""

# defaults are redundant in this module and added to the yaml
# additions to config are noted with `+++` symbols below
spack_tree_defaults = {
	'spot':'./local/spack',
	'spot_envs':'./local/envs-spack',}

spack_mirror_complete = """
import subprocess,re,os
proc = subprocess.Popen('spack -e . concretize -f'.split(),
	stdout=subprocess.PIPE,stderr=subprocess.PIPE)
stdout,stderr = proc.communicate()
if stderr: raise ValueError
specs = [re.match('^.+\\^(.+)$',i).group(1) 
	for i in stdout.decode().splitlines() if re.match('^.+\\^(.+)$',i)]
for spec in specs: 
	os.system(
		'spack buildcache create -m %(mirror)s -a %%s'%%spec)
"""

spack_mirror_complete = """
import subprocess,re,os
proc = subprocess.Popen('spack -e . concretize -f'.split(),
	stdout=subprocess.PIPE,stderr=subprocess.PIPE)
stdout,stderr = proc.communicate()
if stderr: raise ValueError
specs = [re.match('^.+\\^(.+)$',i).group(1) 
	for i in stdout.decode().splitlines() if re.match('^.+\\^(.+)$',i)]
def specbuild(spec=None,cmd=None):
	if not bool(spec) ^ bool(cmd): raise ValueError
	print('[STATUS] buildcache for spec: %%s'%%spec)
	cmd = 'spack buildcache create -m rfcache -a %%s'%%spec
	proc = subprocess.Popen(cmd.split())
	proc.communicate()
	if proc.returncode:
		raise Exception('spack error above')
for spec in specs: specbuild(spec)
specbuild(cmd='spack buildcache create -m %(mirror)s -a %%s'%%spec)
"""

# save time by remembering spack locations
spack_locations = {}

def spack_clone(where=None):
	"""
	Clone a copy of spack for local use.
	"""
	# hardcoded default
	where = where or spack_tree_defaults['spot']
	where = path_resolver(where)
	# split the path to control the clone location
	where_parent = os.path.dirname(where)
	os.makedirs(where_parent,exist_ok=True)
	print('status cloning spack at %s'%where)
	ortho.sync(modules={where:dict(
		address='https://github.com/spack/spack')})
	#! should we have a central conf registrar?
	ortho.conf['spack'] = where
	# +++ add spack location to the conf
	ortho.write_config()
	#! should we confirm the spack clone and commit?
	return ortho.conf['spack']

def spack_init_envs(where=None):
	"""
	Make a directory for spack environments.
	"""
	where = where or spack_tree_defaults['spot_envs']
	where = path_resolver(where)
	if not os.path.isdir(where): 
		print('status initializing spack environments at %s'%where)
		os.makedirs(where,exist_ok=True)
	# +++ add spack envs location to the conf
	ortho.conf['spack_envs'] = where
	ortho.write_config()
	return where

def config_or_make(config_key,builder,where=None):
	"""
	Check the config for a key otherwise build the target.
	"""
	# check the config for the target
	target = ortho.conf.get(config_key,None)
	# without registered key we build the object
	if not target:
		return builder(where=where)
	elif not os.path.isdir(target):
		if os.path.realpath(target)!=os.path.realpath(where):
			print(('warning registered key "%s" points to a missing '
				'directory which means that you created something, it '
				'registered its location, and the location has moved. '
				'we will build to the new target "%s" but the registered '
				'target "%s" may remain.')%(config_key,where,target))
		return builder(where=where)
	else: 
		# account for the fact that cloned spack is in a subdir
		if False and config_key=='spack':
			# spack clone subdirectory is hardcoded here
			target = os.path.join(where,'spack')
		# removed the following message
		if os.path.realpath(target)!=os.path.realpath(where) and 0:
			print(('warning registered target for "%s" is "%s" which is '
				'different than the request "%s"')%(config_key,target,where))
		return target

class SpackEnvMaker(Handler):
	def blank(self): pass
	def _run_via_spack(self,spack_spot,env_spot,command,lmod_decoy_ok=False,fetch=False):
		starter = os.path.join(spack_spot,'share/spack/setup-env.sh')
		#! replace this with a pointer like the ./fac pointer to conda?
		cmd = 'source %s && %s'%(starter,command)
		# when decoy is set and we get the signal from the consumer 
		#   then we proot the lmod location so no changes really apply
		decoy = ortho.conf.get('spack_lmod_decoy',{})
		lmod_decoy = decoy.get('lmod_decoy',None)
		lmod_real = decoy.get('lmod_real',None)
		proot_bin = decoy.get('proot','proot')
		if lmod_decoy_ok and decoy: cmd = '%s -b %s:%s bash -c \'%s\''%(
			proot_bin,lmod_decoy,lmod_real,cmd)
		if lmod_decoy and not os.path.isdir(lmod_decoy):
			os.makedirs(lmod_decoy)
		if lmod_real and not os.path.isdir(lmod_real):
			os.makedirs(lmod_real)
		result = ortho.bash(cmd,announce=True,cwd=env_spot,scroll=not fetch)
		return result
	def std(self,spack,where,spack_spot,cache_mirror=None,cache_only=False):
		os.makedirs(where,exist_ok=True)
		with open(os.path.join(where,'spack.yaml'),'w') as fp:
			yaml.dump({'spack':spack},fp)
		cpu_count_opt = min(multiprocessing.cpu_count(),
			int(os.environ.get('SPACK_MORE_CPUS',6)))
		# flags from CLI passed via meta
		live = self.meta.get('live',False)
		extras = ''
		if cache_only and not live: extras += '--cache-only '
		# inspect the concretize output
		if live:
			command = 'spack --env . concretize %s-f'%(extras)
			#! register this globally for later. somewhat clumsy
			global _LAST_SPACK_ENV
			_LAST_SPACK_ENV = where
		# build for cache by selecting a mirror
		elif cache_mirror:
			# command for the target after we add buildcache dependencies
			command_base = 'spack --env . buildcache create -a -m %s'%cache_mirror
			key_this = ortho.conf.get('spack_buildcache_gpg',None)
			if key_this: command_base += ' -k %s'%key_this
			# write a temporary file to perform this
			result_concretize = self._run_via_spack(
				spack_spot=spack_spot,env_spot=where,
				command='spack -e . concretize -f',fetch=True)
			stdout,stderr = [result_concretize[k] for k in ['stdout','stderr']]
			if stderr: 
				if stdout: print(stdout)
				print(stderr)
				raise Exception('see stderr above')
			regex_dep_hash = r'^\[.\]\s+(.*?)\s+\^(.+)$'
			# get dependencies by hash to avoid collisions when building cache
			specs = [re.match(regex_dep_hash,i).groups() 
				for i in stdout.splitlines() if re.match(regex_dep_hash,i)]
			# we see lots of warnings about existing specs and now there are 2000
			#   for some R pacakages so before we try to build the cache we see if
			#   it already exists. note that this should change if we decide we want
			#   to start overwriteing
			# warning is: ==> Warning: file:///X.spack exists. Use -f option to overwrite.
			if specs:
				# whittle the specs to those that are missing from the build cache
				mirror_dn = ortho.conf.get('spack_mirror_path',None)
				if not mirror_dn:
					raise Exception('spack_mirror_path is not defined in the conf')
				# catalog of all existing tarballs
				tarballs = []  
				for root,dns,fns in os.walk(mirror_dn):
					tarballs.extend([fn for fn in fns
						if re.match('.+\.spack$',fn)])
				# lookup table of all existing specs by hash
				lookup = {}
				for hash_s,spec in specs:
					targets = [i for i in tarballs if re.findall(hash_s,i)]
					if len(targets)==1: lookup[hash_s] = (targets[0],spec)
					elif len(targets)==0: lookup[hash_s] = None
					else: raise Exception('collision on %s,%s'%(hash_s,spec))
				# whittle the specs here
				specs_redux = [(hash_s,spec) for hash_s,spec in specs
					if not (hash_s in lookup and lookup[hash_s])]
				# somehow we have duplicates
				specs_redux = list(set(specs_redux))
				print('[STATUS] collecting the following specs:\n%s'%
					pprint.pformat(specs_redux))
				for hash_s,spec in specs_redux: 
					self._run_via_spack(spack_spot=spack_spot,env_spot=where,
						command=command_base+' /'+hash_s)
			self._run_via_spack(spack_spot=spack_spot,env_spot=where,
				command=command_base)
			return
		# standard installation
		else:
			command = "spack --env . install %s-j %d"%(extras,cpu_count_opt)
		# make fetch happen below because this catches exceptions
		self._run_via_spack(spack_spot=spack_spot,env_spot=where,
			command=command,fetch=False)

class SpackLmodHooks(Handler):
	def write_lua_file(self,modulefile,contents,moduleroot):
		"""Write a custom lua file into the tree."""
		# this recipe does not use spack_lmod_decoy
		with open(os.path.join(moduleroot,modulefile),'w') as fp:
			fp.write(contents)
	def mkdir(self,mkdir):
		# this recipe does not use spack_lmod_decoy
		print('status creating: %s'%mkdir)
		os.makedirs(mkdir,exist_ok=True)	
	def _get_prefix(self):
		prefix = ortho.conf.get('spack_prefix',None)
		if not prefix: raise Exception('cannot find prefix in spack_prefix variable')
		# apply the lmod decoy
		lmod_decoy = ortho.conf.get('spack_lmod_decoy',{})
		if lmod_decoy:
			prefix_lmod = lmod_decoy['lmod_decoy']
			prefix_lmod_real = lmod_decoy['lmod_real']
		else: prefix_lmod = prefix_lmod_real = os.path.join(prefix,'lmod')
		return prefix,prefix_lmod,prefix_lmod_real
	def copy_lua_file(self,custom_modulefile,destination,arch_val,repl=None):
		"""Copy a local lua file into the tree."""
		prefix,prefix_lmod,prefix_lmod_real = self._get_prefix()
		recipes = ortho.conf.get('spack_recipes',None)
		# assume modulefiles are adjacent to the spack_recipes
		fn = os.path.realpath(os.path.join(os.path.dirname(
			recipes),custom_modulefile))
		if not os.path.isdir(prefix):
			raise Exception('%s is not a directory'%prefix)
		if not os.path.isdir(prefix_lmod):
			raise Exception('%s is not a directory'%prefix_lmod)
		dest = os.path.join(prefix_lmod,arch_val,destination)
		with open(fn) as fp: text = fp.read()
		if not repl: repl = {}
		# add the spack_prefix to the repl
		if 'spack_prefix' in repl:
			raise Exception('you cannot use "spack_prefix" in the repl because '
				'it is replaced automatically')
		repl['spack_prefix'] = os.path.join(prefix_lmod_real,arch_val)
		# the REPL_spack_base_prefix should be the root path to spack itself, not Lmod
		#   we use the base for setting paths to the helpers in this case
		#   while the spack prefix is purely for pointing modulefiles to other modulefiles
		repl['spack_base_prefix'] = os.path.join(prefix)
		for k,v in repl.items():
			text = re.sub('REPL_%s'%k,str(v),text)
		print('status writing %s'%destination)
		if not os.path.isdir(os.path.dirname(dest)):
			os.makedirs(os.path.dirname(dest))
		with open(dest,'w') as fp: fp.write(text)
	def intel_parallel_studio_move(self,arch_val,src,dest,clean,modulepath):
		"""Reform the module tree for intel-parallel-studio."""
		#! use more custom arguments to distinguish this from other handler targets
		#!!! check this before executing it in production 
		prefix,prefix_lmod,prefix_lmod_real = self._get_prefix()
		src_lua = os.path.join(prefix_lmod,arch_val,src)
		dest_out = os.path.join(prefix_lmod,arch_val,dest)
		dest_out_dn = os.path.dirname(os.path.join(prefix_lmod,arch_val,dest))
		if not os.path.isdir(dest_out_dn): os.makedirs(dest_out_dn)
		with open(src_lua) as fp: text = fp.read()
		pattern = '^prepend_path\("MODULEPATH",.*?\)$'
		# use the real path below for substitutions to the production paths if decoy
		mod_dn = os.path.join(prefix_lmod_real,arch_val,modulepath)
		if not os.path.isdir(mod_dn): raise Exception('cannot find %s'%mod_dn)
		prepend_modulepath = '-- custom relocation\nprepend_path("MODULEPATH","%s")'%mod_dn
		text_out = re.sub(pattern,prepend_modulepath,text,flags=re.M+re.DOTALL)
		pattern = '^family\("mpi"\)$'
		text_out = re.sub(pattern,'family("compiler")',text_out,flags=re.M+re.DOTALL)
		with open(dest_out,'w') as fp: fp.write(text_out)
		print('status wrote %s'%dest_out)
		clean_dn = os.path.join(prefix_lmod,arch_val,clean)
		print('status removing %s'%clean_dn)		
		shutil.rmtree(clean_dn)
	def default_link(self,arch_val,default):
		#!!! check this before executing it in production 
		prefix,prefix_lmod,prefix_lmod_real = self._get_prefix()
		dn = os.path.dirname(os.path.join(prefix_lmod,arch_val,default))
		fn_src = os.path.join(dn,os.path.basename(default))
		fn_dest = os.path.join(dn,'default')
		#! validate this?
		bash('ln -s %s %s'%(fn_src,fn_dest),scroll=False,v=True)
	def lmod_move(self,arch_val,lmod_fn_src,lmod_fn_dest):
		"""Rename a modulefile."""
		#!!! check this before executing it in production 
		prefix,prefix_lmod,prefix_lmod_real = self._get_prefix()
		base_dn = os.path.join(prefix_lmod,arch_val)
		shutil.move(os.path.join(base_dn,lmod_fn_src),os.path.join(base_dn,lmod_fn_dest))	
	def lmod_sub(self,arch_val,lmod_fn,subs):
		#!!! check this before executing it in production 
		#! see warnings above. make a backup of /data/apps/lmod beforehand
		prefix,prefix_lmod,prefix_lmod_real = self._get_prefix()
		base_dn = os.path.join(prefix_lmod,arch_val)
		target = os.path.join(base_dn,lmod_fn)
		with open(target) as fp: text = fp.read()
		for item in subs:
			text = re.sub(item['k'],item['v'],text,flags=re.M+re.DOTALL)
		with open(target,'w') as fp: fp.write(text)
	def alias_lmod(self,arch_val,target,lmod_alias,hidden=False):
		#!!! check this before executing it in production 
		prefix,prefix_lmod,prefix_lmod_real = self._get_prefix()
		dn = os.path.dirname(os.path.join(prefix_lmod,arch_val,target))
		fn_src = os.path.join(dn,os.path.basename(target))
		if not lmod_alias.endswith('.lua'): lmod_alias += '.lua'
		fn_dest = os.path.join(dn,lmod_alias)
		#! validate this?
		bash('ln -s %s %s'%(fn_src,fn_dest),scroll=False,v=True)
		if hidden:
			# rc is one level up
			rc_fn = os.path.join(os.path.dirname(dn),'.modulerc')
			if os.path.isfile(rc_fn):
				with open(rc_fn) as fp: text = fp.read()
			else: text = '#%Module\n'
			# get the name of this module
			name = os.path.relpath(fn_dest,os.path.dirname(
				os.path.join(os.path.dirname(dn),'.modulerc')))
			name = re.sub('\.lua$','',name)
			hider = 'hide-version %s'%(name)
			# if the hide-version command is absent, add it
			if not re.search(hider,text):
				text = text + '\n%s'%hider
			with open(rc_fn,'w') as fp: fp.write(text)
	
class SpackEnvItem(Handler):
	_internals = {'name':'basename','meta':'meta'}
	def _run_via_spack(self,command,fetch=False,site_force=True,lmod_decoy_ok=False):
		"""Route commands to spack."""
		home_spack = os.path.expanduser('~/.spack')
		if site_force and os.path.isdir(home_spack):
			# disable this due to various issues. this appears to be required
			if os.access(home_spack,os.X_OK | os.W_OK): 
				raise Exception('cannot allow ~/.spack')
			# if spack exists but is not writable we continue
			# we added this feature to identify parts of the workflow that
			#   write to ~/.spack in order to prevent this
			else: pass
		return SpackEnvMaker()._run_via_spack(
			spack_spot=self.meta['spack_dn'],
			env_spot=self.meta['spack_envs_dn'],
			lmod_decoy_ok=lmod_decoy_ok,
			command=command,fetch=fetch)
	def make_env(self,name,specs,mods=None,via=None,
		cache_only=False,cache_mirror=None):
		"""
		Pass this item along to SpackEnvMaker
		If you change the keys above, you must update them below to make sure
		that SpackSeq does not run *other* items when live.
		"""
		# hook to allow cache_mirror from a Handler
		if getattr(cache_mirror,'_is_Handler',False):
			cache_mirror = cache_mirror.solve
		#!!! write environments to a temporary location instead?
		spack_envs_dn = self.meta['spack_envs_dn']
		spack_dn = self.meta['spack_dn']
		spot = os.path.join(spack_envs_dn,name)
		env = {'specs':specs}

		# CUSTOM environment options from the CLI or yaml are managed here
		# supra arguments override the argument
		cache_mirror = self.meta.get('supra',{}).get(
			'cache_mirror',cache_mirror)
		cache_only = self.meta.get('supra',{}).get(
			'cache_only',cache_only)
		# arguments unique to the supra call
		# install_tree sets the target location to install the packages
		install_tree = self.meta.get('supra',{}).get(
			'install_tree',None)
		# install_tree sets the target location to install the packages
		lmod_spot = self.meta.get('supra',{}).get(
			'lmod_spot',None)

		# custom modifications to the environment
		if not mods: mods = {}
		if install_tree:
			# this was updated to include root subkey for a recent spack config
			#   change otherwise you get a "deprecated" error
			delveset(mods,'config','install_tree','root', value=install_tree)
		if lmod_spot:
			try: 
				modules_enable = delve(mods,'modules','enable')
				if not 'lmod' in modules_enable:
					delveset(mods,'modules','enable',
						value=list(modules_enable)+['lmod'])
			except: 
				delveset(mods,'modules','enable',value=['lmod'])
			delveset(mods,'config','module_roots','lmod',
				value=lmod_spot)
		# end of customizations

		# typically use a Handler here but we need meta so simplifying
		if via:
			# start with a template from the parent file in meta
			instruct = copy.deepcopy(self.meta[via])
			# merge the trees
			for route,val in catalog(env):
				delveset(instruct,*route,value=val)
		else: raise Exception('unclear env format')
		if mods:
			for route,val in catalog(mods):
				delveset(instruct,*route,value=val)
		print('status building spack environment at "%s"'%spot)
		# continue to the spack environment interface
		SpackEnvMaker(spack_spot=spack_dn,where=spot,spack=instruct,
			cache_only=cache_only,cache_mirror=cache_mirror,
			# pass through meta for flags e.g. "live" to visit the env
			meta=self.meta)
	def find_compilers(self,find_compilers):
		"""Generic function to find any compilers, for example the system compiler."""
		print('status find_compilers to find any compilers')
		if find_compilers!=None: raise Exception('boostrap must be null')
		self._run_via_spack(command="spack compiler find --scope site")
	def _env_chdir(self,name):
		if name:
			spack_envs_dn = self.meta['spack_envs_dn']
			spot = os.path.join(spack_envs_dn,name)
			if not os.path.isdir(spot):
				raise Exception('cannot find env at: %s'%spot)
			chdir_cmd = "cd %s && "%spot
		else: chdir_cmd = ""
		return chdir_cmd
	def find_compiler(self,find,name=None):
		"""
		Find a compiler, possibly also installed by spack.
		"""
		print('status find_compiler: %s'%find)
		chdir_cmd = self._env_chdir(name)
		# the find argument should be a spec that already exists
		self._run_via_spack(command=chdir_cmd+\
			"PATH=$(spack location -i %s)/bin:$PATH && "
			"spack compiler find --scope site"%find)
	def check_compiler(self,check_compiler):
		"""
		Confirm a background compiler to build against. Combine this
		with careful specification of compilers-built-against-compilers to
		prevent the recompile of a compiler against itself after it is found.
		For example, if you compile gcc 6 against 4 and then use the 
		`find_compiler` function it finds gcc 6 and then if you run the whole
		procedure again and one of your environments requests gcc 6 it will
		assume the default gcc is 6 and try to build gcc 6 against gcc 6 even 
		though it is already built against the background 4.
		"""
		result = self._run_via_spack(command="spack compilers --scope site",fetch=True)
		stdout = result['stdout']
		if not re.match(r'^\w+@[\d\.]+',check_compiler):
			raise Exception('unusual spack spec: %s'%check_compiler)
		if not re.search(check_compiler,stdout):
			raise Exception('failed compiler check: %s'%check_compiler)
	#! the bootstrap and find_compilers and others must take null arguments
	#!   this is unavoidable in the YAML list format when using Handler
	def bootstrap(self,bootstrap):
		"""Bootstrap installs modules."""
		#! this is deprecated from spack and should be removed
		if bootstrap!=None: raise Exception('boostrap must be null')
		self._run_via_spack(command="spack bootstrap")
	def lmod_refresh(self,lmod_refresh,name=None,decoy=False,spack_lmod_hook=None,delete=True):
		"""
		Find a compiler, possibly also installed by spack.
		"""
		if lmod_refresh: raise Exception('lmod_refresh must be null')
		print('status rebuilding Lmod tree')
		chdir_cmd = self._env_chdir(name)
		self._run_via_spack(command=chdir_cmd+\
			# always delete and rebuild the entire tree
			"spack -e . module lmod refresh %s-y"%('--delete-tree ' if delete else ''),
			# decoy asks the spack run to check spack_lmod_decoy
			lmod_decoy_ok=decoy)
	def lmod_hooks(self,lmod_hooks):
		"""Look over lmod hook objects."""
		for item in lmod_hooks: SpackLmodHooks(**item).solve
	def lmod_hide_nested(self,lmod_hide_nested):
		"""
		Remove nested Lmod paths from spack.
		Ported via script-hide-nested-lmod.py
		e.g. removes m1/linux-centos7-x86_64/gcc/7.4.0/openmpi/3.1.4-4dhlcnc/hdf5/1.10.5.lua
		"""
		print('status cleaning nested modules')
		# hardcoded 7-character hashes
		regex_nested_hashed = '(.+)-[0-9a-z]{7}$'
		spot = os.path.realpath(lmod_hide_nested)
		if not os.path.isdir(spot):
			raise Exception('cannot find %s'%spot)
		result = {}
		for root,dns,fns in os.walk(spot):
			path = root.split(os.path.sep)
			if len(path)>=2 and re.match(regex_nested_hashed,path[-2]):
				base = os.path.sep.join(path[:-3])
				if base not in result: result[base] = []
				result[base].extend([os.path.sep.join(path[-3:]+[
					re.match(r'^(.+)\.lua$',f).group(1)]) for f in fns])
		for key,val in result.items():
			fn = os.path.join(key,'.modulerc')
			print('writing %s'%fn)
			with open(fn,'w') as fp:
				fp.write('#%Module\n')
				for item in val:
					fp.write('hide-version %s\n'%item)
	def lmod_remove_nested_hashes(self,lmod_remove_nested_hashes):
		"""
		Incompatible with `lmod_hide_nested_hashes`. 
		Make the openmpi modules more transparent.
		DEPRECATED. This prevents the use of a default module. 
		  This method likely deviates too far from the usual Lmod scheme.
		Options: remove all of the nested openmpi or not. 
		You cannot keep the nesting and remove the hashes while using defaults.
    	via: lmod_remove_nested_hashes: *module-spot
		"""
		#! repeated from above
		# hardcoded 7-character hashes
		regex_nested_hashed = '(.+)-[0-9a-z]{7}$'
		spot = os.path.realpath(lmod_remove_nested_hashes)
		if not os.path.isdir(spot):
			raise Exception('cannot find %s'%spot)
		result = {}
		for root,dns,fns in os.walk(spot):
			path = root.split(os.path.sep)
			if len(path)>=2 and re.match(regex_nested_hashed,path[-2]):
				base = os.path.sep.join(path[:-3])
				if base not in result: result[base] = []
				result[base].extend([os.path.sep.join(path[-3:]+[
					re.match(r'^(.+)\.lua$',f).group(1)]) for f in fns])
		for key,vals in result.items():
			root = list(set([os.path.sep.join(
				val.split(os.path.sep)[:2]) for val in vals]))
			if len(root)!=1: raise Exception('inconsistent roots')
			target = vals[0].split(os.path.sep)[:2]
			hashed_name = target[1]
			simple_name = re.match(regex_nested_hashed,hashed_name).group(1)
			dest = os.path.join(key,target[0],simple_name)
			target_dn = os.path.join(key,os.path.sep.join(target))
			bash('mv %s %s'%(target_dn,dest),scroll=False,v=True)
			# replace the hash in the modulefile
			fns_hashed = glob.glob(dest+'.lua')
			if len(fns_hashed)!=1:
				raise Exception('failed to replace hashes')
			target = fns_hashed[0]
			print('status replacing "%s" with "%s" in: %s'%(
				hashed_name,simple_name,target))
			with open(target) as fp: text = fp.read()
			text = re.sub(hashed_name,simple_name,text)
			with open(target,'w') as fp: fp.write(text)
	def lmod_defaults(self,lmod_defaults):
		"""Create links for lmod defaults."""
		for fn in lmod_defaults:
			if not os.path.isfile(fn):
				raise Exception('cannot find %s'%fn)	
			dirname = os.path.dirname(fn)
			bash('ln -s %s %s'%(os.path.basename(fn),'default'),
				cwd=dirname,scroll=False,v=True)
	def _check_mirror(self,mirror_name,spot=None):
		result = self._run_via_spack('spack mirror list',fetch=True)
		if result['stderr']: raise OSError
		mirrors = dict([i.split() for i in result['stdout'].splitlines()])
		if mirror_name not in mirrors: return False
		if spot:
			spot_dn = os.path.realpath(spot)
			spot_abs = 'file://%s'%spot_dn
			if mirrors[mirror_name]!=spot_abs:
				#! add html options
				raise Exception('mirror %s exists but we cannot confirm it is '
					'located at is at %s'%(mirror_name,spot_abs))
		return True
	def make_mirror(self,mirror_name,spot):
		#! no spot checking so you cannot change the spot and thereby move it
		if self._check_mirror(mirror_name,spot=spot): return
		spot_dn = os.path.realpath(spot)
		self._run_via_spack('spack mirror add --scope site %s %s'%(
			mirror_name,spot_dn))
		return mirror_name
	def lmod_simplify(self,lmod_simplify,
		compiler,compiler_version,arch_val,targets):
		"""
		Lmod simplification designed for Rockfish.
		STATUS: this method has two benefits
		  1. swappable python-dependent modules
			 for example, if you load python/3.8.6 and then py-numpy, you can switch python versions
			 and switching to python/3.7.9 will reload the *correct* py-numpy (otherwise module error)
			 and it will also deactivate any modules that do not exist
		  2. retains the autoload feature from spack
		  3. ml spider still tells you which packages to load
		  3. cleaner module tree with a separate section for python-dependent modules to reduce clutter
        Further modification with `hash_s` below allows us to also move openmpi/3.1.6-xyzxyzx.
		"""
		if lmod_simplify: raise Exception('lmod_refresh must be null')
		print('status simplify lmod tree')
		prefix = ortho.conf.get('spack_prefix',None)
		if not prefix: raise Exception('cannot find prefix in spack_prefix variable')
		if not os.path.isdir(prefix):
			raise Exception('%s is not a directory'%prefix)
		# standard lmod prefix
		prefix_lmod = os.path.join(prefix,'lmod')
		# override if decoy
		lmod_decoy = ortho.conf.get('spack_lmod_decoy',{})
		if lmod_decoy: prefix_lmod = lmod_decoy['lmod_decoy']
		base = os.path.join(prefix_lmod,arch_val,compiler,compiler_version)
		# we hardcode an alt directory to avoid cluttered nesting
		dest = os.path.join(prefix_lmod,arch_val,'alt',compiler,compiler_version)
		# retain the real name for substitutions if we are using decoy
		dest_real = os.path.join(prefix,'lmod',arch_val,'alt',compiler,compiler_version)
		if not os.path.isdir(base):
			#! raise Exception('cannot find %s'%base)
			os.makedirs(base)
		print('status base is %s'%base)
		if not os.path.isdir(dest):
			print('status making %s'%dest)
			os.makedirs(dest)
		for target_spec in targets:
			# we allow some extra customizations so we can also move openmpi
			is_mpi = False
			if isinstance(target_spec,dict):
				name = target_spec['name']
				version = target_spec['version']
				hash_s = target_spec['hash']
				is_mpi = target_spec.get('is_mpi',False)
				if 'name_alt' in target_spec: 
					name_out = target_spec['name_alt']
				else: name_out = name
				if 'version_alt' in target_spec:
					version_out = target_spec['version_alt']
				else: version_out = version
				alt_module = target_spec.get('alt_module',False)
			else: 
				name,version = target_spec.split('@')
				family = name
				hash_s = None
				name_out,version_out = name,version
				alt_module = False
			target = os.path.join(base,name,version)
			if hash_s: target += '-%s'%hash_s
			# step 1: remove the complicated tree from 
			# move the targets (anythin in the e.g. python/3.8.6 directory) to an alt location 
			# note that this does not move python/3.8.6.lua which remains in the main tree
			dest_this = os.path.join(dest,name_out)
			# real name in case decoy
			dest_this_real = os.path.join(dest_real,name_out)
			if not os.path.isdir(dest_this):
				os.makedirs(dest_this)
			print('status moving %s to %s'%(target,os.path.join(dest_this,version)))
			#! path dependency problem here; the directory already exists
			dn_out = os.path.join(dest_this,version_out)
			if not os.path.isdir(dn_out):
				if not os.path.isdir(os.path.dirname(dn_out)):
					os.makedirs(os.path.dirname(dn_out))
				os.rename(target,dn_out)
			# step 2: when parent is loaded we add the moved tree to the MODULEPATH
			fn_parent = target+'.lua'
			# custom move instructions for openmpi/3.1.6-xyzxyzx
			if is_mpi and not alt_module:
				tree_new = os.path.join(dest_this_real,version)
				fn_parent = os.path.join(base,name,version_out+'.lua')
				with open(fn_parent) as fp: text = fp.read()
				pattern = '^prepend_path\("MODULEPATH",.*?\)$'
				prepend_modulepath = '-- custom relocation\nprepend_path("MODULEPATH","%s")'%tree_new
				text_out = re.sub(pattern,prepend_modulepath,text,flags=re.M+re.DOTALL)
				with open(fn_parent,'w') as fp: fp.write(text_out)
				# we do not need to do the regex replacements that were
				#   necessary for packages like Python and R which used projections
				#   because openmpi is automatically projected to a special hashed path
				# however we must be very careful to avoid openmpi collisions
				continue
			# alternate modulefile for moving intel-parallel-studio
			elif alt_module:
				recipes = ortho.conf.get('spack_recipes',None)
				tree_new = os.path.join(dest_this_real,version_out)
				# assume modulefiles are adjacent to the spack_recipes
				fn_src = os.path.realpath(os.path.join(os.path.dirname(
					recipes),alt_module))
				with open(fn_src) as fp: text = fp.read()
				# lots of control flow here but this is unavoidable
				repls = {'version':version_out,'mpi_version':'%s-%s'%(version,hash_s),'modulepath':tree_new}
				for k,v in repls.items(): text = re.sub('REPL_%s'%k,v,text)
				fn_out = os.path.join(base,name_out,version_out+'.lua')
				dn_out = os.path.dirname(fn_out)
				if not os.path.isdir(dn_out): os.makedirs(dn_out)
				with open(fn_out,'w') as fp: fp.write(text)
				print('status wrote %s'%fn_out)
			# no need to customize the parent if we have alt module
			if not alt_module:
				print('status customizing %s'%fn_parent)
				with open(fn_parent,'a') as fp:
					fp.write('-- customization: move the view projection for subordinate packages\n')
					fp.write('-- then add the moved tree to the MODULEPATH\n')
					dn_parent_root = os.path.join(dest_this_real,version)
					# we prepend as a matter of taste. spack prepends too which means the most 
					#   important features, including the compiler and base apps are at the bottom
					#   which sometimes makes them easier to see. like an inverted pyramid
					fp.write('prepend_path("MODULEPATH","%s")\n'%dn_parent_root)	
					fp.write('family("%s")'%family)
			# step 3: walk the moved tree and replace items
			dest_this = os.path.join(dest,name_out,version_out)
			print('status walking %s'%dest_this)
			lua_fns = []
			for root,dn,fns in os.walk(dest_this,topdown=False):
				lua_fns.extend([os.path.join(root,i) for i in fns if re.match('^.+\.lua$',i)])
			# the loader requirements ensure that prereq is correct when we move 
			#   the intel-parallel-studio items into the correct place in the hierarchy
			if 'loader_req' in target_spec:
				name = target_spec['loader']['name']
				version = target_spec['loader']['version']
			for fn in lua_fns:
				print('status modifying %s'%fn)
				with open(fn) as fp: text = fp.read()
				# pattern to find the parent which must be loaded already anyway since we moved
				#   the tree out of the way. we replace with a prereq to enforce this
				regex_parent_load = 'if not isloaded\("%s\/%s"\) then.*?end'%(name,version)
				repl = '-- customize: ensure parent is loaded\nprereq("%s/%s")'%(name,version)
				found = re.findall(regex_parent_load,text,flags=re.M+re.DOTALL)
				text_out = re.sub(regex_parent_load,repl,text,flags=re.M+re.DOTALL)
				# most upstream modules from autoload: direct or all in spack will now have 
				#   the wrong path since after the move so we remove the nesting
				# note that the nesting is created by a view projection in spack to enable 
				#   this separation between supporting modules
				text_out = re.sub('"%s\/%s\/'%(name,version),'"',text_out,flags=re.M+re.DOTALL)
				with open(fn,'w') as fp: fp.write(text_out)
	def copy(self,source,prefix_subpath):
		"""
		Copy files into the spack prefix.
		"""
		#! lazy, possibly unsafe
		src = os.path.join(source,'')
		# destination is relative to the prefix
		prefix = ortho.conf.get('spack_prefix',None)
		if not prefix: raise Exception('cannot find spack_prefix')
		dest = os.path.join(prefix,prefix_subpath,'')
		cmd = 'rsync -arivP --delete %s %s'%(src,dest)
		print('status running: %s'%cmd)
		os.system(cmd)
	def copyfile(self,filename,prefix_subpath):
		"""
		Copy files into the spack prefix.
		"""
		# destination is relative to the prefix
		prefix = ortho.conf.get('spack_prefix',None)
		if not prefix: raise Exception('cannot find spack_prefix')
		dest = os.path.join(prefix,prefix_subpath,'')
		if not os.path.isdir(dest):
			os.makedirs(dest)
		shutil.copyfile(filename,os.path.join(dest,os.path.basename(filename)))
	def instruct_lmod_decoy(self,instruct_lmod_decoy):
		"""Tell the admin how to deploy the tree if using a decoy.""" 
		decoy = ortho.conf.get('spack_lmod_decoy',{})
		if decoy:
			print('status you have spack_lmod_decoy set, so we have build the '
				'lmod tree at %s'%decoy['lmod_decoy'])
			decoy_dn,real_dn = [os.path.join(decoy[k],'') for k in ['lmod_decoy','lmod_real']]
			alt_dn = re.sub('lmod','backup-lmod',real_dn)
			print('status we recommend the following backup, deployment (and rescue) procedure:')
			cmd = 'sudo rsync -arivP --delete %s %s'
			lines = [cmd%(real_dn,alt_dn)+' && '+cmd%(decoy_dn,real_dn),cmd%(alt_dn,real_dn)]
			for line in lines: print(' '+line)
			print('warning you should check your work before deploying in production')
	def renviron_hpc_mods(self,env,specs,reps,rprofile_coda=None,renviron_mods=None):
		"""Update the Renviron paths for HPC environments."""
		if renviron_mods: raise Exception('renviron must be null')
		spack_envs_dn = self.meta['spack_envs_dn']
		spot = os.path.join(spack_envs_dn,env)
		for spec,form in specs.items():
			#! skipping _run_via_spack because not clear on how to handle cwd
			#!   and anyway we only run this as admin with the spack command loaded
			result = ortho.bash('spack env activate . && spack location -i %s'%spec,
				scroll=False,cwd=spot)
			if result['stderr']: raise Exception(result['stderr'])
			# modify the Renviron
			prefix = result['stdout'].strip('\n')
			if 'r' not in spack_locations: spack_locations['r'] = []
			spack_locations['r'].append(prefix)
			fn = os.path.join(prefix,'rlib/R/etc/Renviron')
			with open(fn) as fp: text = fp.read()
			text_out = re.sub('^R_LIBS_USER.*?\n','# rockfish mods\n'
				'R_LIBS_USER=${R_LIBS_USER-\'%s\'}\n'%
				form,text,flags=re.M+re.DOTALL)
			# extra replacements
			for k,v in reps.items(): text_out = re.sub(k,v,text_out,flags=re.M+re.DOTALL)
			with open(fn,'w') as fp: fp.write(text_out)
			# add to the Rprofile according to tags
			fn = os.path.join(result['stdout'].strip('\n'),'rlib/R/library/base/R/Rprofile')
			with open(fn) as fp: text = fp.read()
			if not rprofile_coda: rprofile_coda = {}
			for item in rprofile_coda:
				tag = item['tag']
				content = item['content']
				if not re.search(tag,text):
					text += tag+'\n'+content+'\n'
			with open(fn,'w') as fp: fp.write(text)
	def instruct_r_python_protect(self,instruct_r_python_protect=None,):
		"""Update the Renviron paths for HPC environments."""
		if instruct_r_python_protect: raise ValueError
		# use this recipe after r_hpc_mods to produce some chomd commands
		#   that help protect our R installations from accidental install.packages
		#   from the admin who installed the software
		lines = []
		for item in spack_locations.get('r',[]):
			lines.append(' sudo find %s -name rlib -type d -exec chmod -R a-w {} \;'%item)
			lines.append(' sudo find %s -name Renviron -type f -exec chmod u+w {} \;'%item)
			lines.append(' sudo find %s -name Rprofile -type f -exec chmod u+w {} \;'%item)
		print('warning do not install packages as admin')
		print('\n'.join(lines))
		print('warning use the chmod commands above to protect R libs paths')
	def instruct_custom(self,instruct_custom):
		"""Print generic instructions."""
		print('status generic instructions')
		for item in instruct_custom:
			print(' %s'%str(item))
		print('warning see generic instructions above')

def spack_env_maker(what):
	"""
	Command line interface to install a spack environment.
	#! previously this was exposed to the CLI so you could directly
	#!   use a yaml in a spack environment
	"""
	spack = ortho.conf.get('spack',None)
	if not spack: spack_clone()
	with open(what) as fp: 
		instruct = yaml.load(fp,Loader=yaml.SafeLoader)
	SpackEnvMaker(spack_spot=spack,**instruct).solve

class SpackSeq(Handler):
	def seq_envs(self,envs,notes=None):
		"""
		Install a sequence of spack environments.
		"""
		# configure paths from parent: self.meta
		spack_dn = config_or_make(
			config_key='spack',builder=spack_clone,
			where=self.meta.get('spot'))
		spack_envs_dn = config_or_make(
			config_key='spack_envs',builder=spack_init_envs,
			where=self.meta.get('spot_envs'))
		self.meta['spack_dn'] = spack_dn
		self.meta['spack_envs_dn'] = spack_envs_dn
		for env in envs: 
			# pass along the live flag via meta from CLI
			# filter out anything that is not environment when live
			# the following must match the make_env signature
			keys_make_env = {'name','specs','mods',
				'via','cache_only','cache_mirror'}
			# skip items that are not routed to make_env
			if self.meta.get('live',True) and not env.keys()<=keys_make_env:
				continue
			SpackEnvItem(meta=self.meta,**env)

class SpackSeqSub(Handler):
	_internals = {'name':'basename','meta':'meta'}
	def subselect(self,name,tree,live=False):
		"""
		One file and one choice (the name selects 
		part of the tree to run). 
		#! Consider a name for this pattern?
		"""
		self.name = name
		# builtin defaults from a dictionary above
		self.tree = copy.deepcopy(spack_tree_defaults)
		self.tree.update(**tree)
		# pass through the live flag from the CLI
		self.tree['live'] = live
		self.deploy = SpackSeq(meta=self.tree,**tree[name])
		return self

def spack_tree(what,name,live=False,**meta):
	"""
	Install a sequence of spack environments.
	Previously we linked this to `make spack` but this was retired to
	`make spack_tree` in specs/cli_spack.yaml.
	"""
	notes = """
		reqs:
			lib/spack.py
			specs/spack_tree.yaml
			specs/cli_spack.yaml
		use:
			make use specs/cli_spack.yaml
			make spack_tree specs/spack_tree.yaml seq01
		pseudocode:
			command provides a file and a name
			name is a key in the file
			SpackSeqSub has the global scope of the file in meta
			and sends the subtree keyed by name to SpackSeq
			which use Handler to install packages with spack
		clean:
			rm -rf config.json local && \
			python -c "import ortho;ortho.conf['replicator_recipes'] = 
			'specs/recipes/*.yaml';ortho.write_config(ortho.conf)" 
			&& make use specs/cli_spack.yaml
		test:
			make spack_tree specs/spack_tree.yaml gromacs_gcc6
	"""
	requires_python_check('yaml')
	import yaml
	print('status installing spack seq from %s with name %s'%(what,name))
	with open(what) as fp: 
		tree = yaml.load(fp,Loader=yaml.Loader)
	# meta arguments percolate to downstream functions
	#   however we already later use meta for the tree, so we add supra-meta
	#   arguments here as supra
	if meta:
		if 'supra' in tree: raise KeyError
		tree['supra'] = meta
	spack = SpackSeqSub(name=name,tree=tree,live=live).solve
	# assume no changes to the tree, it has a spot, and the spot is parent
	spack_spot = ortho.path_resolver(tree['spot'])
	# register the spack location
	return CacheChange(spack=spack_spot)

### Spack HPC deployment for Blue Crab

def spack_hpc_decoy(spec,name=None,live=False,
	tmpdir=None,factory_site=None,mounts=None,image=None,decoy_method='proot'):
	"""
	Operate spack in a decoy environment
	See `spack_hpc_run` for instructions.
	This function can be called directly with `make do` or using the 
	  wrapper function below via `make spack_hpc_deploy`.
	"""
	spack_hpc_singularity_deploy_script = '\n'.join([
		'export TMPDIR=%(tmpdir)s',
		'export TMP_DIR=%(tmpdir)s',
		'cd %(factory_site)s',
		'# assume the min environment is available with yaml',
		#! make the env name flexible
		'source env.sh min',
		'./fac spack %(spec)s %(target)s %(flags)s',
		'echo "[STATUS] you are inside the decoy environment!"'])
	factory_site = os.getcwd() if not factory_site else factory_site
	#! do not call this from the CLI. remove from cli_spack.yaml
	# check if we are in a slurm job
	if not os.environ.get('SLURM_JOBID',None):
		raise Exception('this command must run inside slurm')
	# build a temporary script which we can run inside the singularity container
	# ideally the user only runs one instance so the script is a token
	script_token = 'container-spack-hpc.sh'
	if os.path.isfile(script_token):
		raise Exception('cannot execute when %s exists'%script_token)
	# ask user for the name
	#! untested after major changes. moved to lib.generic.menu
	if not name:
		with open(spec) as fp:
			text = yaml.load(fp,Loader=yaml.Loader)
		print('status available targets:')
		#! very clusmy
		opts_num = dict(list(zip(*(zip(enumerate(text.keys())))))[0]) 
		print('\n'.join(['  {:3d}: {:s}'.format(ii+1,i) for ii,i in enumerate(text.keys())]))
		asker = (input if sys.version_info>(3,0) else raw_input)
		select = asker('select a target: ')
		if select.isdigit() and int(select)-1 in opts_num:
			name = opts_num[int(select)-1]
		elif select.isdigit():
			raise Exception('invalid number %d'%int(select))
		elif select not in text:
			raise Exception('invalid selection "%s"'%select)
	# settings
	detail = {
		'spec':spec,
		'target':name,
		'factory_site':factory_site,
		'tmpdir':tmpdir,
		'flags':' live' if live else ' '}
	if any(not i for i in detail.values()):
		raise Exception('empty value in detail: %s'%str(detail))
	# prepare the script
	script_text = spack_hpc_singularity_deploy_script.strip()%detail
	print('status script for singularity follows')
	print(script_text)
	# prepare the mounts
	mounts_out = []
	for item in mounts:
		this = {}
		if item.keys()=={'host'}:
			this['host'] = this['local'] = item['host']
		elif item.keys()=={'host','local'}:
			this = item
		else: raise Exception('invalid: %s'%str(this))
		mounts_out.append((this['host'],this['local']))
	mounts_out.append((detail['tmpdir'],detail['tmpdir']))
	mounts = ['%s:%s'%(i,j) for i,j in mounts_out]
	absent_dns = [i for i,j in mounts_out 
		if not os.path.isdir(i) and not os.path.isfile(i)]
	if any(absent_dns):
		raise Exception('missing: %s'%str(absent_dns))
	print('status mounts follow')
	print('\n'.join(mounts))
	#! check existence of host directories and image or let singularity?
	if decoy_method=='proot': cmd = (
		#! need a flexible proot location
		"/software/apps/proot/5.1.0/bin/proot "+
		" ".join(['-b %s'%i for i in mounts])+" "
		"/bin/bash -c 'cd %s && "%detail['factory_site'])
	elif decoy_method=='singularity': cmd = (
		"ml singularity && SINGULARITY_BINDPATH= "+
		"singularity "+("shell " if live else "run ")+ 
		" ".join(['-B %s'%i for i in mounts])+
		" "+image+" "+"-c 'cd %s && "%detail['factory_site'])
	else: raise Exception('invalid decoy method: %s'%decoy_method)
	if live:
		spack_envs_dn = ortho.conf.get('spack_envs',None)
		# to figure out the right env we would have to read the spec file here
		#   so instead we just go to the environments folder
		if spack_envs_dn: envs_cd = 'cd %s && '%os.path.realpath(spack_envs_dn)
		else: envs_cd = ''
		postscript = (" source env.sh spack && %s"%envs_cd+
			"export TMPDIR=%s &&"%detail['tmpdir'])
		cmd += ("/bin/bash %s &&%s /bin/bash --norc'"%(script_token,postscript))
	else: cmd += "/bin/bash %s'"%script_token
	print('status running: %s'%cmd)
	# execution loop
	try:
		with open(script_token,'w') as fp:
			fp.write(script_text)
		#! security hole
		os.system(cmd)
	# failure and cleanup
	except:
		print('error received error during spack_hpc_deploy')
		print('error cleaning up token/script at %s'%script_token)
		os.remove(script_token)
		print('error done cleaning')
		raise
	print('status done and removing %s'%script_token)
	os.remove(script_token)
	print('status exiting')

def read_deploy(deploy,entire=False):
	"""Interpret a deploy file without directly executing it."""
	# note that we cannot edit the deploy yaml in place so we read without tags
	#   then apply overrides, then pass the result to `spack_hpc_decoy`.
	with open(deploy) as fp: text = fp.read()
	# use the correct python tag to subvert the call to the function
	# the following trick therefore accomplishes the override
	target_tag = 'tag:yaml.org,2002:python/object/apply:lib.spack.spack_hpc_decoy'
	# use safe loader otherwise reading the deploy yaml triggers the tag
	from ortho.yaml_mods import YAMLTagFilter,select_yaml_tag_filter
	tree = yaml.load(text,Loader=YAMLTagFilter(target_tag))
	deliver = select_yaml_tag_filter(tree,target_tag)
	# the deliver tree would normally go right to spack_hpc_decoy via `make do`
	#   so we pick off kwds and send it there after overrides
	if deliver.keys()>{'kwds','test'}:
		raise Exception('invalid %s in %s with keys: %s'%(
			target_tag,deploy,str(deliver.keys())))
	return deliver

def spack_hpc_deploy(deploy,name=None,live=False,spec=None):
	"""
	Run spack in a decoy environment. This can be called from `spack_hpc_run`.
	We can run this directly via:
	  ./fac spack_hpc_deploy specs/spack_hpc_deploy.yaml \
	    --name=bc-std --decoy_method=proot --spec=specs/spack_hpc.yaml --live
	"""
	deliver = read_deploy(deploy)
	kwargs = deliver['kwds']
	# override the deploy file with incoming kwargs
	kwargs['live'] = live
	if name: kwargs['name'] = name
	if spec: kwargs['spec'] = spec
	# run the decoy environment
	print('status calling spack_decoy with: %s'%str(kwargs))
	spack_hpc_decoy(**kwargs)	

def spack_hpc_test_visit(deploy):
	"""Test a spack build before production using deploy notes."""
	deliver = read_deploy(deploy,entire=True)
	# include the test command with keywords to decoy
	cmd = deliver.get('test',None)
	if not cmd: raise Exception('cannot find "test" in %s'%deploy)
	print('status running: %s'%cmd)
	os.system(cmd)

def spack_hpc_run(run=None,deploy=None,
	spec=None,live=False,test=False,**kwargs):
	"""
	Prepare a call to SLURM to build software with spack.
	This script takes the place of a bash script to kickoff new jobs.
	Usage:
	  make spack_hpc_run \
        run=specs/spack_hpc_run.yaml \
	    deploy=specs/spack_hpc_deploy.yaml \
        spec=specs/spack_hpc.yaml \
        name=bc-std live
	The run file can define the deploy file to supply the remaining arguments.
	"""
	print('status preparing to use spack')
	# collapse flags at the CLI into a single decoy_method
	# fold default kwargs into one object
	kwargs.update(run=run,spec=spec,deploy=deploy,live=live)
	if not run: raise Exception('we require a run file')
	# a yaml tag allows the CLI to override the run file 
	def yaml_tag_flag(self,node):
		scalar = self.construct_scalar(node)
		if scalar not in kwargs: 
			if test and scalar=='name': return "testing"
			raise Exception('cannot get this flag from the cli: %s'%scalar)
		else: return kwargs[scalar]
	yaml.add_constructor('!flag',yaml_tag_flag)
	# load the run file
	with open(run) as fp: 
		detail = yaml.load(fp,Loader=yaml.Loader)
	# contents check
	if detail.keys()>{'docs','settings'}:
		raise Exception('run file has invalid format: %s'%str(detail))
	settings = detail['settings']
	#! beware no use of kwargs unless you use the `!flag` tag in the run file
	# prepare the script we will execute in SLURM
	script = [
		'cd %s'%os.getcwd(),
		# use the venv to provide the environment or override
		'source env.sh %s'%settings.get('env_name','venv')]
	if 'sbatch' in settings:
		script += ['module purge']
	if not settings['deploy']: raise Exception('no deploy file')
	# call the spack_hpc_deploy function with the deploy file and name
	script += ['./fac spack_hpc_deploy %s --name=%s'%(settings['deploy'],settings['name'])]
	# pass the spec through
	if spec: script[-1] += ' --spec=%s'%spec
	if live and test:
		raise Exception('cannot use live and test at the same time')
	# prepare an salloc command
	if live:
		cmd = ['salloc']
		script[-1] += ' --live'
		cmd.extend(['%s=%s'%(i,j) 
			for i,j in settings.get('sbatch',{}).items()])
		cmd.extend(["srun --pty /bin/bash -c '%s'"%' && '.join(script)])
	# test the code by visiting 
	elif test:
		spack_hpc_test_visit(deploy=deploy)
		return
	else: 
		cmd = ['sbatch']
		cmd.extend(['%s=%s'%(i,j) 
			for i,j in settings.get('sbatch',{}).items()])
		script_fn = 'script-spack-build.sh'
		script = ['#!/bin/bash',
			'trap "{ rm -f %s; }" EXIT ERR'%script_fn]+script
		with open(script_fn,'w') as fp: fp.write('\n'.join(script))
		cmd += [script_fn]
	cmd_out = ' '.join(cmd)
	print('status running command: %s'%cmd_out)
	# using os.system for the PTY
	os.system(cmd_out)

### Refactor Spack on Rockfish 

## detritus

def spack_seq_alt(envs,ref=None):
	"""Use a spack_tree recipe in a parent yaml file."""
	"""
	retired this method from rockfish.yaml but here is the spec for posterity
	  # DEMO: preliminary setup
	  # usage: make spack specs/rockfish.yaml setup_explicit
	  # this demo creates spack environments directly from this file
	  # see alternate setup: make specs/rockfish.yaml go do=full 
	  setup_explicit:
	    # talk directly to lib.spack in the same format as spack_tree.yaml
	    # the first step compilest the code however the setup select deploys
	    - !!python/object/apply:lib.spack.spack_seq_alt
	      kwds:
	        ref: *spec
	        envs:
	          - find_compilers: null
	          - name: env_lmod
	            via: template_basic
	            specs: ['lmod']
	    # repeat to the cache mirror
	    - !!python/object/apply:lib.spack.spack_seq_alt
	      kwds:
	        ref: *spec
	        envs:
	          - find_compilers: null
	          - name: env_lmod
	            via: template_basic
	            specs: ['lmod']
	            cache_mirror: !!python/object/apply:lib.spack.SpackMirror 
	              kwds: *mirror
	    # this do item is redundant with the lmod spec above
	    - !!python/object/apply:lib.spack.spack_install_cache
	      kwds:
	        spec: *spec
	        target: *prefix
	        do: lmod_base
	"""
	# we use the SpackSeqSub not for subselecting but to get other variables 
	#   from the spack_rockfish.yaml file with another pointer for modularity
	tree = dict(only=dict(envs=envs))
	# refer to a file to use a config in a via
	if ref:
		with open(ref) as fp: tree.update(**yaml.load(fp))
	SpackSeqSub(name='only',tree=tree)

## router functions

"""
redundancy note. the typical spack_tree installation allows you to map simple 
configuration files in yaml into a spack environment which we then either 
inspect (concretize) or install. when developing more elaborate workflows, we
would typically use the "via" flag in SpackEnvItem.make_env
"""

def spack_router(spec,sub,debug=False,slurm=False,**kwargs):
	"""Catchall spack builds and deployment."""
	#! example usage: make spack specs/rockfish.yaml t03 do=gromacs slurm
	if not os.path.isfile(spec):
		raise Exception('cannot find %s'%spec)
	print('status received kwargs: %s'%kwargs)
	# reformulate incomming command line arguments
	yaml_do_select(
		# standard arguments
		what=spec,name=sub,debug=debug,
		# custom arguments
		slurm=slurm,**kwargs)

def spack_hpc_shortcut(sub,debug=False,slurm=False,**kwargs):
	"""Shortcut to call the router with a spec set by a make use operation."""
	# see specs/cli_spack.yaml rockfish recipe for an example
	return spack_router(sub=sub,debug=False,slurm=False,**kwargs)

def conda_shared(reqs,target_ortho_key):
	"""Build a shared conda environment. Useful for HPC admins."""
	spot = ortho.conf.get(target_ortho_key,None)
	if not spot: 
		raise Exception(('you must set `make set %s <path>`'
			'to point to the anaconda installation')%target_ortho_key)
	if not os.path.isfile(reqs):
		raise Exception('argument must be a conda requirements file')	
	spot_envs = os.path.join(spot,'envs')
	# note that the name is set in the reqs file but the path is the same
	#   as the conda requirements base file name
	print('warning you may need to set permissions:')
	print(('export CONDA_SPOT=%s && '
		'sudo find $CONDA_SPOT -type f -exec chmod g+rw {} \; &&'
		'sudo find $CONDA_SPOT -type d -exec chmod g+rwx {} \; ')%spot_envs)
	print('warning if you get permission denied you must fix permissions')
	if not os.path.isdir(spot_envs):
		raise Exception('cannot find %s'%spot_envs)
	print('status building environment from %s'%reqs)
	init_sh = os.path.join(spot,'etc','profile.d','conda.sh')
	env_path = os.path.join(spot_envs,
		re.sub('\.(.*?)$','',os.path.basename(reqs)))
	print('status env path is %s'%env_path)
	bash('source %s && conda env update --file %s -p %s'%(
		init_sh,reqs,env_path),announce=True)

def spack_env_install(spec,do,target=None):
	print('status building environment %s from %s'%(do,spec))
	spack_tree(what=spec,name=do,install_tree=target)

def spack_env_concretize(spec,do,target=None,visit=False):
	print('status building environment %s from %s'%(do,spec))
	tree = spack_tree(what=spec,name=do,install_tree=target,live=True)
	#!! dev: hack to get the environment from globals. note that we need
	#!!   a minor refactor to make this more elegant
	if '_LAST_SPACK_ENV' in globals():
		#! can we change directory? probably not but it would be useful
		print('status spack environment spot: %s'%_LAST_SPACK_ENV)

@incoming_handlers
def spack_env_cache(spec,do,cache_mirror=None):
	print('status making buildcache for environment %s from %s'%(do,spec))
	#! the following is clumsy
	if not cache_mirror: raise Exception('needs cache_mirror')
	spack_tree(what=spec,name=do,
		# custom supra-meta arguments
		cache_mirror=cache_mirror)

def spack_install_cache(spec,do,target,modules=None):
	"""Deploy the code to another tree from a build cache."""
	target = os.path.abspath(os.path.expanduser(target))
	if not modules:
		# place lmod files in a subdirectory
		modules = os.path.join(target,'lmod')
	print('status installing to %s'%target)
	spack_tree(what=spec,name=do,
		# custom supra-meta arguments
		# we insist on a cache build, choose an alternate location, and 
		#   ensure that the lmod modules are build nearby
		cache_only=True,install_tree=target,lmod_spot=modules)

## spack supervision

class SpackMirror(Handler):
	_protected = {'realname','meta'}
	_internals = {'name':'realname','meta':'meta'}
	def make_mirror(self,name,spot):
		SpackSeqSub(name='only',tree=dict(only=dict(envs=[dict(
			mirror_name=name,spot=spot)])))
		return name
