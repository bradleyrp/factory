#!/usr/bin/env python

"""
Replicator REDEVELOPMENT
Rebuild a replicator feature to replace ortho.replicator, specifically `repl`.
"""

import os,re,tempfile,subprocess,string,sys,shutil,copy
#! refer to ortho by name for top-level imports simplified by init?
from ..bash import bash
from ..dictionary import DotDict
from ..handler import Handler
from ..requires import requires_program,is_terminal_command
from ..requires import requires_python_check
from ..misc import path_resolver
from .templates import screen_maker

def mount_macos(dmg,mount):
	"""
	Mount an image in macos.
	"""
	# assume it is mounted if the directory exists
	if not os.path.isdir(mount):
		bash('hdiutil attach -nobrowse -mountpoint %s %s'%(mount,dmg))
	return mount

class SpotPath(Handler):
	"""
	Handle a path for docker.
	"""
	def macos_mount(self,dmg,mount):
		"""
		Mount a dmg file.
		This interpreter takes a spot from the config created 
		by lib.macos.MacosImager and passes along a hook for mounting.
		"""
		mount_macos(dmg,mount)
		return dict(fs='dmg',path=mount)
	def local(self,local): 
		"""
		Default local path to a spot.
		"""
		return dict(path=local)

class Volume(Handler):
	"""
	Handle external volumes for a replicator.
	Note that this class is used by the Volume class exposed to yaml.
	For extra volume tuning see 'consistent' at: 
		https://docs.docker.com/docker-for-mac/osxfs-caching/
	"""
	def _check_darwin(self):
		if sys.platform=='darwin':
			raise Exception('Your platform is darwin. '
				'We require a hook to mount a case-sensitive filesystem. '
				'If you already have one, this is a development exception '
				'and we need to detect the case-sensitivity directly.')

	def docker(self,docker):
		"""Use a docker volume."""
		volumes = bash('docker volume ls -q',scroll=False,v=True)
		avail = volumes['stdout'].split()
		if docker not in avail:
			print('status adding docker volume %s'%docker)
			out = bash('docker volume create %s'%docker,scroll=False,v=True)
		else: print('status found docker volume %s'%docker)
		#! hardcoded link to the outside should be configurable
		args_out = ('-v %s:%%s'%docker)%'/home/user/outside'
		return dict(name=docker,docker_args=args_out)

	def _local(self,path):
		path = path_resolver(path)
		args_out = '-v %s:%s -w %s'%(path,path,path)
		return dict(docker_args=args_out)

	def local(self,local):
		"""Add the current directory to the volume."""
		path = local
		self._check_darwin()
		path = path_resolver(path)
		args_out = '-v %s:%s -w %s'%(path,path,path)
		return dict(docker_args=args_out)

	def local_fs(self,path,fs):
		# in this use case we mount an extra path as well as the pwd
		#! this is designed for macos mounts with a non-root mount
		if fs!='dmg': self._check_darwin()
		path = path_resolver(path)
		pwd = path_resolver(os.getcwd())
		args_out = '-v %s:%s -v %s:%s -w %s'%(path,path,pwd,pwd,pwd)
		return dict(docker_args=args_out)

class DockerFileMaker(Handler):
	#! this replicates ortho.replicator.replicator.DockerFileMaker
	#!   however there are several features which need to be ported in
	def raw(self,raw,dockerfiles_index=None):
		"""Set a verbatim Dockerfile under the raw key."""
		# note that we ignore other keys when we have the raw file
		self.dockerfile = raw
	def sequence(self,series,dockerfiles_index):
		"""Construct a dockerfile from a set of components."""
		dockerfile = []
		for item in series:
			item_lookup = dockerfiles_index.get(item,None)
			if not item_lookup:
				raise Exception('cannot find dockerfile: %s'%item)
			comment = '# dockerfile from series: %s\n'%item
			dockerfile.append(comment)
			#! no substitution feature yet
			dockerfile.append(item_lookup)
		self.dockerfile = '\n'.join(dockerfile)
		print('status dockerfile follows')
		print('\n'.join(['| '+i for i in self.dockerfile.splitlines()]))

class DockerContainer(Handler):
	_internals = {'name':'real_name','meta':'meta'}
	def get_container(self,name):
		"""Get an existing container by name."""
		# get the repo and tag from the docker name
		try: repo,name = re.match('^(.+):(.+)$',name).groups()
		except: 
			raise Exception(
				'docker container name must be <repo>:<tag> but we got: %s:%s'%
				name)
		print('status checking containers')
		containers = bash(
			'docker images --format "{{.Repository}} {{.Tag}}"',
			scroll=False,v=True)
		avail = [tuple(i.split()) for i in containers['stdout'].splitlines()]
		translate_none = lambda x: None if x=='<none>' else x
		avail = [tuple(translate_none(i) for i in j) for j in avail]
		avail = [(i,j) for i,j in avail if not (i==None and j==None)]
		if (repo,name) in avail:
			return '%s:%s'%(repo,name)
		#! is this a possible outcome?
		elif repo==None and (None,name) in avail: 
			return name
		# rather than build here we defer to ReplicateCore._docker_compose
		else: return False

class DockerExecution(Handler):
	def line(self,line):
		"""
		Turn a script into a one-liner for a `docker run` command.
		Not suitable for complex scripts with variable substitutions.
		"""
		regex_hashbang = r'^(#!.*?s*\n)?(.+)$'
		match = re.match(regex_hashbang,line,flags=re.M+re.DOTALL)
		hashbang,contents = re.match(
			regex_hashbang,line,flags=re.M+re.DOTALL).groups()
		# confirm bash or sh hashbang
		if hashbang:
			hashbang_path = re.match(r'^#!(.*?)\s*$',hashbang).group(1)
			if hashbang_path not in ['/bin/bash','/bin/sh']:
				raise Exception('invalid hashbang for one-liner to docker: %s'%
					hashbang_path)
		# fix quotes
		contents_safe = re.sub('"','\\"',contents.strip('\n'))
		return dict(line='%s'%contents_safe,kind='line')
	def script(self,script):
		"""Scripts pass through to the function that calls docker."""
		return dict(script=script,kind='script')

class ScriptPrelim(Handler):
	def fileprep(self,files=None,specs=None):
		staged = {}
		# specs are yaml trees that are dumped to files
		if specs:
			for name,tree in specs.items():
				with tempfile.NamedTemporaryFile(delete=False) as fp:
					tmp_fn = fp.name
					fp.write(yaml.dump(tree).encode())
					fp.close()
				staged[name] = tmp_fn
		return staged

def constructor_site_hook(loader,node):
	"""
	Use this as a constructor for the `!spots` yaml tag to get an alternate
	location for running something. Works with SpotPath and sends to Volume.
	"""
	name = loader.construct_scalar(node)
	# process the site
	from ortho import conf
	spots = conf.get('spots',{})
	if name in spots: 
		return SpotPath(**spots[name]).solve
	# the root keyword points to the local directory
	elif name=='root': return dict(local='./')
	# pass through the name for a literal path
	else: return dict(local=name)

def subselect_hook(loader,node):
	"""Select a portion of a recipe."""
	# see twin function get_recupe_subselector to unpack this
	subtree = loader.construct_mapping(node)
	def tree_subselect(name=None):
		"""Promote a child node to the parent to whittle a tree."""
		if not name: return subtree
		else: return subtree.get(name)
	return tree_subselect

def get_recipe_subselector(recipe):
	"""Unpack a subtree."""
	subsel_hook_name = [i for i,j in recipe.items() 
		if j.__class__.__name__=='function' 
		and j.__name__=='tree_subselect']
	if len(subsel_hook_name)!=1:
		if len(subsel_hook_name)>1:
			msg = '. matching keys are: %s'%subsel_hook_name
		else: msg = ''
		raise Exeception('failed to uniquely identify a tree_subselect '
			'function populated from the !select tag'+msg)
	else: select_func = recipe.pop(subsel_hook_name[0])
	return select_func

def spec_import_hook(loader,node):
	"""Import another spec file."""
	requires_python_check('yaml')
	import yaml
	this = loader.construct_mapping(node)
	parent_fn = loader.name
	if not os.path.isfile(parent_fn):
		raise Exception('failed to check file: %s'%parent_fn)
	# import from the other file as either relative or absolute path
	path = os.path.join(os.path.dirname(parent_fn),this['from'])
	if not os.path.isfile(path):
		path = os.path.realpath(this['from'])
		if not os.path.isfile(path):
			raise Exception('cannot find: %s'%this['from'])
	with open(path) as fp: 
		imported = yaml.load(fp,Loader=yaml.Loader)
	if this['what'] not in imported:
		raise Exception('cannot find %s in %s'%(this['what'],this['from']))
	return imported[this['what']]

# package hooks
yaml_hooks_recipes_default = {
	'!spots':constructor_site_hook,
	'!select':subselect_hook,
	'!import_spec':spec_import_hook,}

class RecipeRead(Handler):
	"""Interpret the reproducibility recipes."""
	verbose = True
	yaml = None

	def _get_yaml(self):
		"""Import yaml once inside this class."""
		#! this saves some repetition but probably does not improve speed
		if not self.yaml: 
			requires_python_check('yaml')
			import yaml
			self.yaml = yaml
		return self.yaml

	def _add_hooks(self,**hooks):
		yaml = self._get_yaml()
		# load the default hooks
		for name,hook in yaml_hooks_recipes_default.items():
			yaml.add_constructor(name,hook)
		# +++ HOOKS are loaded here
		if hooks:
			for name,hook in hooks.items():
				yaml.add_constructor(name,hook)

	def explicit_path(self,path,hooks=None): 
		"""Process a recipe from an explicit path."""
		if not hooks: hooks = {}
		yaml = self._get_yaml()
		self._add_hooks(**hooks)
		with open(path) as fp: 
			recipe = yaml.load(fp,Loader=yaml.Loader)
		return dict(recipe=recipe)

	def subselect(self,path,subselect_name,hooks=None):
		"""
		Assemble a recipe from multiple recipes in a single file.
		This recipe is triggered by a subselect_name which comes from the CLI
		specifically via `make docker <spec> <name>` and the rest follows below.
		"""
		if not hooks: hooks = {}
		yaml = self._get_yaml()
		self._add_hooks(**hooks)
		with open(path) as fp: 
			recipe = yaml.load(fp,Loader=yaml.Loader)
		recipe_full = copy.deepcopy(recipe)
		"""
		pseudocode: the subselect method requires:
			a recipe with only one select tree
			a name in that select tree
			possibly importing other codes
		"""
		# identify the item in the spec file that provides a selection
		select_func = get_recipe_subselector(recipe)
		# make the selection
		selected = select_func(subselect_name)
		if not selected:
			raise Exception('cannot find selection: %s'%subselect_name)
		return dict(recipe=selected,ref=recipe,parent=recipe_full)

class ReplicateCore(Handler):
	"""
	DEV: replacement for the replicator functions
	"""

	def _docker_compose(self,image,dockerfile,compose,
		compose_cmd=None,mode='build',visit=False,
		cleanup=True,dockerfiles_index=None):
		"""
		Run the standard docker-compose loop.
		Note that ReplicateCore._docker can be used to run docker with a 
		preexisting image otherwise you need the present function to build.
		"""
		# the default mode is build for a command to be specified later
		if mode=='build':
			if compose_cmd:
				raise Exception(
					'cannot set compose_cmd if mode is build: %s'%compose_cmd)
			compose_cmd = 'docker-compose build'
		elif mode=='compose':
			if not compose_cmd:
				raise Exception('compose mode requires a compose_cmd')
		else: raise Exception('invalid mode: %s'%mode)
		requires_python_check('yaml')
		import yaml
		if not dockerfile or not compose:
			raise Exception('we require dockerfile and compose arguments')
		#! account for self.spot['docker_args'] possible collision with compose
		# run compose build in a temorary location
		dn = tempfile.mkdtemp()
		# build the Dockerfile
		dockerfile_obj = DockerFileMaker(dockerfiles_index=dockerfiles_index,
			**dockerfile)
		# run compose from the temporary location
		try:
			print('status compose from %s'%dn)
			#! link here instead with ln_name? in case you are visiting?
			with open(os.path.join(dn,'Dockerfile'),'w') as fp:
				fp.write(dockerfile_obj.dockerfile)
			with open(os.path.join(dn,'docker-compose.yml'),'w') as fp:
				yaml.dump(compose,fp)
			# run docker compose
			if visit:
				# we require a TTY to enter the container so we use os.system
				# possible security issue
				# this requires `visit: True` in the recipe alongside command
				print('status running docker: %s'%compose_cmd)
				here = os.getcwd()
				os.chdir(dn)
				os.system(compose_cmd)
				os.chdir(here)
			else:
				# background execution
				bash(compose_cmd,cwd=dn,v=True)
		except Exception as e:
			# leave no trace
			shutil.rmtree(dn)
			raise
		# cleanup
		if cleanup:
			shutil.rmtree(dn)
			# send this back for self.container
			# note that the user must ensure that the image name in the compose 
			#   file matches the image_name in the recipe. docker handles the rest
			# the following serves as a check that the image was created
			return DockerContainer(name=image).solve
		# if not cleaning up we return the temporary directory
		else: return dn

	def _docker(self,image,volume={},
		compose_bundle=None,rebuild=False,mode=None,nickname=None,visit=False,
		**kwargs):
		"""
		Run a one-liner command in docker.
		Not suitable for complex bash commands.
		"""
		# you cannot use decorators with Handler
		is_terminal_command('docker')
		if not mode: raise Exception('docker function requires a mode')

		# step 1: assemble the volume
		self.spot = Volume(**volume).solve
		docker_args = self.spot['docker_args']

		# step 2: locate the container
		self.container = DockerContainer(name=image).solve
		# if no container we redirect to _docker_compose if we are visiting
		#   because a visit will create a manual docker command
		if (not self.container or rebuild) and mode=='visit':
			self.container = self._docker_compose(image=image,**compose_bundle)
		# we can run a command directly in the docker-compose folder
		elif mode=='compose':

			# nickname is a simple method for preventing reexecution
			# the nickname links us to the temporary location of the compose
			# the nickname comes from the name kwarg to `make docker`
			ln_name = 'up-%s'%nickname
			if nickname and (
				os.path.isfile(ln_name) or os.path.islink(ln_name)):
				raise Exception(('found link %s which might indicate that '
					'these containers are up. remove to continue.'%ln_name))

			# kwargs contains either line or script for the execution step
			self.do = DockerExecution(**kwargs).solve
			if self.do['kind']=='line':
				compose_cmd = self.do['line']
			elif self.do['kind']=='script':
				raise Exception('dev')
			else: raise Exception('dev')

			# note that the container may exist at this point but either way
			#   we still need to run compose with the right command
			spot = self._docker_compose(image=image,mode='compose',visit=visit,
				compose_cmd=compose_cmd,cleanup=False,**compose_bundle)
			# note that execution concludes with compose when the recipe
			#   specifies a command. we report the compose location
			print('status docker-compose runs from: %s'%spot)
			os.symlink(spot,ln_name)
			print('status linked to %s'%ln_name)
			return

		elif not self.container:
			raise Exception('failed to get a container')
		elif mode=='visit': pass
		else: raise Exception('dev')

		# remaining execution occurs with a manual command
		if mode=='visit':

			# run docker commands without compose if you turn off visit here
			visit_direct = True
			# reformat the docker call if necessary
			self.do = DockerExecution(**kwargs).solve
			# in the visit mode we reformulate a docker command
			if docker_args: docker_args += ' '
			# removed "-u 0" which runs as root
			# wrap the command in a `docker run` with arguments and volumes
			cmd = 'docker run -i%s %s%s'%('t' if visit_direct else '',
				docker_args,self.container)
			# case A: one-liner
			if self.do['kind']=='line':
				cmd += ' /bin/sh -c "%s"'%self.do['line']
			# case B: write a script
			elif self.do['kind']=='script': pass
			else: raise Exception('dev')

			# execute the docker run command
			#! stdout for the script is clumsy because of newlines, escape
			# script execution via stdin to docker
			if self.do['kind']=='script':
				script = self.do['script']
				print('status script:\n'+str(script))
				print('status command: %s'%cmd)
				proc = subprocess.Popen(cmd.split(),stdin=subprocess.PIPE)
				proc.communicate(script.encode())
			
			# we require a TTY to enter the container so we use os.system
			elif visit_direct:

				# possible security issue
				print('status running docker: %s'%cmd)
				os.system(cmd)
			
			# standard execution
			else: bash(cmd,scroll=True,v=True)

		else: raise Exception('dev')
	
	def docker_mimic(self,image,volume,nickname=None,visit=False,**kwargs):
		"""
		Run a docker container in "mimic" mode where it substitutes for the
		host operation system and maintains the right paths.
		"""
		print('status running ReplicateCore.docker_mimic')
		return self._docker(volume=volume,image=image,
			visit=visit,nickname=nickname,**kwargs)

	def screen(self,screen,script,**kwargs):
		"""
		Run something in a screen.
		"""
		print('status starting a screen named: %s'%screen)
		spot = kwargs.pop('spot',None)
		# spillover kwargs go to a ScriptPrelim class
		if kwargs: prelim = ScriptPrelim(**kwargs).solve
		else: prelim = {}
		# prepare a location
		if spot and not os.path.isdir(spot): 
			os.mkdir(spot)
			spot = path_resolver(spot)
		# detect string interpolation
		#! finish this feature! protect against wonky scripts
		if 0:
			formatter = string.Formatter()
			reqs = formatter.parse(script)
			#! set trace here
		script = script%dict(spot=spot if spot else '')
		# add staged variables to the script
		if prelim:
			staged_flag = 'staged here'
			if not re.search(r'#\s*%s\s*'%staged_flag,script):
				raise Exception('we have variables for injection into your '
					'script. please include a comment "%s" in the script'%
					staged_flag)
			else:
				#! scape sequences below
				variable_injection = '# injected variables\n' + \
					'\n'.join(['%s="%s"'%(i,j) for i,j in prelim.items()])+'\n'
				script = re.sub(r'#\s*%s\s*'%staged_flag,
					variable_injection,script)
		# prepare the execution script
		screen_log = os.path.join(os.getcwd(),'screen-%s.log'%screen)
		detail = dict(screen_name=screen,contents=script,screen_log=screen_log,
			prelim='' if not spot else '\ncd %s'%spot)
		with tempfile.NamedTemporaryFile(delete=False) as fp:
			tmp_fn = fp.name
			# the CLEANUP_FILES are deleted at the end of the screened script
			detail['post'] = "\nCLEANUP_FILES=%s"%fp.name
			fp.write((screen_maker%detail).encode())
			fp.close()
		print('status executing temporary script: %s'%tmp_fn)
		bash('bash %s'%tmp_fn,v=True)
		if os.path.isfile(tmp_fn): os.remove(tmp_fn)
		tmp_screen_conf = 'screen-%s.tmp'%screen
		#! the following caused a race condition
		#!   if os.path.isfile(tmp_screen_conf): os.remove(tmp_screen_conf)

	def direct_raw(self,script): 
		return self._direct(script=script,spot=None)

	def direct_spot(self,script,spot): 
		return self._direct(script=script,spot=spot)

	def _direct(self,script,**kwargs):
		#!!! function is hidden because collision with script. fix later
		"""
		Run a script directly.
		"""
		spot = kwargs.pop('spot',None)
		if kwargs: prelim = ScriptPrelim(**kwargs).solve
		else: prelim = {}
		# prepare a location
		if spot and not os.path.isdir(spot): os.mkdir(spot)
		elif not spot: spot = './'
		script = script%dict(spot=os.path.abspath(spot))
		# add staged variables to the script
		if prelim:
			staged_flag = 'staged here'
			if not re.search(r'#\s*%s\s*'%staged_flag,script):
				raise Exception('we have variables for injection into your '
					'script. please include a comment "%s" in the script'%
					staged_flag)
			else:
				#! scape sequences below
				variable_injection = '# injected variables\n' + \
					'\n'.join(['%s="%s"'%(i,j) for i,j in prelim.items()])+'\n'
				script = re.sub(r'#\s*%s\s*'%staged_flag,
					variable_injection,script)
		with tempfile.NamedTemporaryFile(delete=False) as fp:
			tmp_fn = fp.name
			fp.write(script.encode())
			fp.close()
		print('status executing temporary script: %s'%tmp_fn)
		bash('bash %s'%tmp_fn,v=True,cwd=spot)
