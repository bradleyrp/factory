#!/usr/bin/env python

from ortho import Handler,requires_python_check
from ortho.yaml_mods import YAMLObjectInit
import copy,sys,os

class OrthoSync(YAMLObjectInit):
	"""Trivial wrapper around ortho sync."""
	yaml_tag = '!ortho_sync'
	def __init__(self,**kwargs):
		self.sources = kwargs
		if kwargs.get('until',False): return
		else: self._run()
	def _run(self):
		# reformulate the modules
		kwargs_out = {}
		for key in self.sources:
			spot = self.sources[key]['spot']
			if spot in kwargs_out:
				raise Exception('repeated key: %s'%spot)
			kwargs_out[spot] = dict([(i,j) 
				for i,j in self.sources[key].items()
				if i!='spot'])
		from ortho import sync
		sync(modules=kwargs_out)

### specification file patterns

class FileNameSubSelector(Handler):
	_internals = {'name':'basename','meta':'meta'}
	defaults = {} # placeholder for later
	Target = None
	def subselect(self,file,name,**kwargs):
		"""
		This handler implements the file/name pattern.
		"""
		requires_python_check('yaml')
		import yaml
		#! from SpackSeqSub, replace it!
		with open(file) as fp: 
			tree = yaml.load(fp,Loader=yaml.SafeLoader)
		self.name = name
		# builtin defaults from a dictionary above
		self.tree = copy.deepcopy(self.defaults)
		self.tree.update(**tree)
		self.deploy = self.Target(meta=self.tree,**tree[name],**kwargs)
		return self

class RunScript(Handler):
	def script(self,script,spot=None):
		from ortho.replicator.replicator_dev import ReplicateCore
		ReplicateCore(script=script,spot=spot)

### YAML examples

class ExampleYAMLClass(YAMLObjectInit):
	"""An example class called via yaml."""
	yaml_tag = "!example_yaml_class"
	def __init__(self,*args,**kwargs):
		print(('status created %s object with: '
			'args = %s and kwargs = %s'%(self.__class__.__name__,
				str(args),str(kwargs))))
		self.args = args
		self.kwargs = kwargs
		# cli.Interface.do discards the object so we take action here
		self.method()
	def method(self):
		"""Example method."""
		print('status example method for %s'%self)
		print('status the object is: %s'%str(self.__dict__))

def example_yaml_function(*args,**kwargs):
	"""An example function called via yaml."""
	print('args = %s and kwargs = %s'%(str(args),str(kwargs)))
	# the following return value goes back to cli.Interface.do and is unused
	return 'meaningless'

### interface tools

def menu(**kwargs):
	"""Ask the user to select a command."""
	import pdb;pdb.set_trace()
	# automatic selection via keyword name
	name = kwargs.pop('name',False)
	if name: pass
	# manual selection
	else:
		print('status available targets:')
		#! very clusmy
		opts_num = dict(sorted(zip(*(zip(enumerate(kwargs.keys())))))[0]) 
		print('\n'.join(['  {:3d}: {:s}'.format(ii+1,i) for ii,i in enumerate(kwargs.keys())]))
		asker = (input if sys.version_info>(3,0) else raw_input)
		select = asker('select a target: ')
		if select.isdigit() and int(select)-1 in opts_num:
			name = opts_num[int(select)-1]
		elif select.isdigit():
			raise Exception('invalid number %d'%int(select))
		elif select not in kwargs:
			raise Exception('invalid selection "%s"'%select)
		else: name = select
	from ortho import bash
	target = kwargs[name]
	if isinstance(target,dict):
		if target.keys()=={'cmd','vars'}:
			subs = {}
			for key in target['vars']:
				key_env = 'menu_%s'%key
				if key_env in os.environ: subs[key] = os.environ[key_env]
				else: subs[key] = asker('enter "%s": '%key)
			cmd_out = target['cmd']%subs
		else: raise Exception('invalid selection: %s'%str(target))
	else: cmd_out = target
	os.system(cmd_out)
