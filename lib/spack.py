#!/usr/bin/env python

#! manually pick up the overloaded print
from __future__ import print_function
import os,copy,re,sys,glob
import ortho
import multiprocessing
# several functions below use yaml 
#! we typically use the requirement function to load yaml in each function
try:
	import yaml
	from lib.yaml_mods import YAMLObjectInit
	# loading yaml_mods adds extra tags and constructors
	from ortho.yaml_mods import yaml_tag_strcat_custom,yaml_tag_merge_lists
	# chain feature for handling dependencies
	yaml.add_constructor('!chain',yaml_tag_strcat_custom(" ^"))
	# additional shorthand
	yaml.add_constructor('!str',yaml_tag_strcat_custom(" "))
	yaml.add_constructor('!strflush',yaml_tag_strcat_custom(""))
	def yaml_tag_loop_r_packages(self,node):
		this = self.construct_mapping(node)
		if this.keys()!={'base','loop'}:
			raise Exception('invalid format: %s'%str(this))
		return ['%s %s'%(i,this['base']) for i in this['loop']]
	yaml.add_constructor('!loopcat',yaml_tag_loop_r_packages)
except Exception as e: 
	#! yaml error here if you raise
	#! hence this is loaded twice. consider fixing? or explicate
	pass
from ortho import Handler
from ortho import CacheChange
from ortho import path_resolver
from ortho import catalog
from ortho import delveset
from ortho import requires_python_check
from ortho import bash

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
		if os.path.realpath(target)!=os.path.realpath(where):
			print(('warning registered target for "%s" is "%s" which is '
				'different than the request "%s"')%(config_key,target,where))
		return target

class SpackEnvMaker(Handler):
	def blank(self): pass
	def _run_via_spack(self,spack_spot,env_spot,command,fetch=False):
		starter = os.path.join(spack_spot,'share/spack/setup-env.sh')
		#! replace this with a pointer like the ./fac pointer to conda?
		result = ortho.bash('source %s && %s'%
			(starter,command),announce=True,cwd=env_spot,scroll=not fetch)
		return result
	def std(self,spack,where,spack_spot):
		os.makedirs(where,exist_ok=True)
		with open(os.path.join(where,'spack.yaml'),'w') as fp:
			yaml.dump({'spack':spack},fp)
		cpu_count_opt = min(multiprocessing.cpu_count(),6)
		# flags from CLI passed via meta
		live = self.meta.get('live',False)
		if not live: command = 'spack install -j %d'%cpu_count_opt
		else: command = 'spack concretize -f'
		self._run_via_spack(spack_spot=spack_spot,env_spot=where,
			command=command)

class SpackLmodHooks(Handler):
	def write_lua_file(self,modulefile,contents,moduleroot):
		"""Write a custom lua file into the tree."""
		with open(os.path.join(moduleroot,modulefile),'w') as fp:
			fp.write(contents)
	def mkdir(self,mkdir):
		print('status creating: %s'%mkdir)
		os.makedirs(mkdir,exist_ok=True)	

class SpackEnvItem(Handler):
	_internals = {'name':'basename','meta':'meta'}
	def _run_via_spack(self,command,fetch=False,site_force=True):
		"""Route commands to spack."""
		if site_force and os.path.isdir(os.path.expanduser('~/.spack')):
			raise Exception('cannot allow ~/.spack')
		return SpackEnvMaker()._run_via_spack(
			spack_spot=self.meta['spack_dn'],
			env_spot=self.meta['spack_envs_dn'],
			command=command,fetch=fetch)
	def make_env(self,name,specs,mods=None,via=None):
		"""
		Pass this item along to SpackEnvMaker
		"""
		spack_envs_dn = self.meta['spack_envs_dn']
		spack_dn = self.meta['spack_dn']
		spot = os.path.join(spack_envs_dn,name)
		env = {'specs':specs}
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
		SpackEnvMaker(spack_spot=spack_dn,where=spot,spack=instruct,
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
		if bootstrap!=None: raise Exception('boostrap must be null')
		self._run_via_spack(command="spack bootstrap")
	def lmod_refresh(self,lmod_refresh,name=None,spack_lmod_hook=None):
		"""
		Find a compiler, possibly also installed by spack.
		"""
		if lmod_refresh: raise Exception('lmod_refresh must be null')
		print('status rebuilding Lmod tree')
		chdir_cmd = self._env_chdir(name)
		self._run_via_spack(command=chdir_cmd+\
			# always delete and rebuild the entire tree
			"spack module lmod refresh --delete-tree -y")
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
			#! should we allow live only in certain cases?
			# pass along the live flag via meta from CLI
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

def spack_tree(what,name,live=False):
	"""
	Install a sequence of spack environments.
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
	spack = SpackSeqSub(name=name,tree=tree,live=live).solve
	# assume no changes to the tree, it has a spot, and the spot is parent
	spack_spot = ortho.path_resolver(tree['spot'])
	# register the spack location
	return CacheChange(spack=spack_spot)

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
