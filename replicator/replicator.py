#!/usr/bin/env python

#from __future__ import print_function
from ortho.requires import requires_python
from ortho.dictionary import MultiDict
from ortho import bash
import re,tempfile,os
import datetime as dt
import uuid

__all__ = ['tester','test_clean','test_help']

### TOOLS

class SpotLocal:
	"""Make a local directory."""
	#! needs cleanup option
	def __init__(self,site=None):
		"""Make a local folder."""
		if not site:
			ts = dt.datetime.now().strftime('%Y%m%d%H%M') 
			code = uuid.uuid4().hex[:2].upper()
			self.path = 'repl_%s.%s'%(ts,code)
			os.mkdir('./%s'%self.path)
		else: 
			self.path = site
			os.mkdir(site)

class Runner:
	"""Execute a file with Bash."""
	def __init__(self,**kwargs):
		self.script = kwargs.pop('script')
		self.cwd = kwargs.pop('cwd')
		self.log = kwargs.pop('log','log')
		self.fn = kwargs.pop('fn')
		self.path_full = self.script_fn = os.path.join(self.cwd,self.fn)
		self.local_bash = kwargs.pop('local_bash',False)
		if False:
			self.path = os.path.basename(path)
			self.cwd = os.path.dirname(path)
			self.log = log
			self.subs = dict(path=self.path)
			self.cmd = kwargs.pop('cmd','bash %(path)s')%self.subs
		self.subs = dict(path=self.script_fn,fn=self.fn)
		self.cmd = kwargs.pop('cmd','bash %(fn)s')%self.subs
		if kwargs: raise Exception('unprocessed kwargs: %s'%kwargs)
		self.run()
	def run(self):
		if self.script:
			with open(self.path_full,'w') as fp: fp.write(self.script)
		bash(self.cmd,cwd=self.cwd,log=os.path.join(self.cwd,self.log),local=self.local_bash)

class Handler:
	taxonomy = {}
	def classify(self,*args):
		matches = [name for name,keys in self.taxonomy.items() if (
			(isinstance(keys,set) and keys==set(args)) or 
			(isinstance(keys,dict) and set(keys.keys())=={'base','opts'} 
				and set(args)>=keys['base']))]
		if len(matches)==0: 
			raise Exception('cannot classify instructions with keys: %s'%list(args))
		elif len(matches)>1: 
			raise Exception('redundant matches: %s'%matches)
		else: return matches[0]
	def __init__(self,name=None,meta=None,**kwargs):
		if not name: self.name = "UnNamed"
		self.meta = meta if meta else {}
		fname = self.classify(*kwargs.keys())
		if not hasattr(self,fname): 
			raise Exception(
				'development error: taxonomy name "%s" is not a member'%fname)
		# introspect on the function to make sure the keys 
		#   in the taxonomy match the available keys in the function?
		getattr(self,fname)(**kwargs)

class ReplicatorSpecial(Handler):
	taxonomy = {
		'dockerfiles':{'dockerfiles'},}
	def dockerfiles(self,**kwargs):
		self.dockerfiles = kwargs.pop('dockerfiles')
		if kwargs: raise Exception

class DockerFileChunk(Handler):
	taxonomy = {
		'substitutes':{'text','subs'},}
	def substitutes(self,text,subs):
		self.text = text%subs

class DockerFileMaker(Handler):
	taxonomy = {
		'sequence':{'sequence'},}
	def sequence(self,sequence):
		"""Assemble a sequence of dockerfiles."""
		index = MultiDict(base=self.meta['dockerfiles'].dockerfiles,underscores=True)
		self.dockerfile = '\n'.join([self.refine(index[i]) for i in sequence])
	def refine(self,this):
		"""Refine the Dockerfiles."""
		if isinstance(this,dict): 
			return DockerFileChunk(**this).text
		else: return this

### SUPERVISOR

class ReplicatorGuide(Handler):
	taxonomy = {
		'simple':{'script'},
		'simple_docker':{'base':{'script','dockerfile','tag'},'opts':{'site'}},}

	def simple(self,script):
		"""
		Execute a script.
		"""
		spot = SpotLocal()
		run = Runner(script=script,fn='script.sh',cwd=spot.path)

	def simple_docker(self,script,dockerfile,tag,site=None):
		"""
		Run a script in a docker container.
		"""
		dfm = DockerFileMaker(meta=self.meta,**dockerfile)
		spot = SpotLocal(site=site)
		with open(os.path.join(spot.path,'Dockerfile'),'w') as fp: 
			fp.write(dfm.dockerfile)
		script_build = '\n'.join([
			'docker build -t %s .'%tag,])
		# write the script before building the docker
		with open(os.path.join(spot.path,'script.sh'),'w') as fp: 
			fp.write(script)
		run = Runner(script=script_build,fn='script_build.sh',
			log='log-build',cwd=spot.path,local_bash=False)
		run = Runner(script=None,
			#! note that this name needs to match the COPY command in Docker
			cwd=spot.path,fn='script.sh',log='log-run',
			cmd='docker run %s'%tag)#+' %(path)s')

### READERS

@requires_python('yaml')
def replicator_read_yaml(source,name=None):
	"""
	Read a replicator instruction and send it to the Guide for execution.
	"""
	import yaml
	with open(source) as fp: 
		# we load into a MultiDict to forbid spaces (replaced with underscores) in top-level dictionary.
		instruct = MultiDict(base=yaml.load(fp.read()),underscores=True,strict=True)
	# special handling
	reference = {}
	for key in ReplicatorSpecial.taxonomy:
		if key in instruct: 
			reference[key] = ReplicatorSpecial(name=key,**{key:instruct.pop(key)})
	# leftovers from special handling must be tests
	if not name and len(instruct)>1: 
		raise Exception(
			('found multiple keys in source %s. you must choose '
				'one with the name argument: %s')%(source,instruct.keys()))
	elif not name and len(instruct)==1: 
		test_name = instruct.keys()[0]
		print('status','found one instruction in source %s: %s'%(source,test_name))
	elif name:test_name = name
	else: raise Exception('source %s is empty'%source)
	test_detail = instruct[test_name]
	return dict(name=test_name,detail=test_detail,meta=reference)

### INTERFACE

def test_clean():
	os.system(' rm -rf repl_*')

def tester(**kwargs):
	"""
	Run a test.
	Disambiguates incoming test format and sends it to the right reader.
	Requires explicit kwargs from the command line.
	"""
	# read the request according to format
	if (set(kwargs.keys())<={'source','name'} 
		and re.match(r'^(.*)\.(yaml|yml)$',kwargs['source'])):
		this_test = replicator_read_yaml(**kwargs)
	else: raise Exception('unclear request')
	# run the replicator
	rg = ReplicatorGuide(name=this_test['name'],
		meta=this_test['meta'],**this_test['detail'])

def test_help():
	#!!! retire this eventually
	print('make tester source=deploy_v1.yaml name=simple_test')
	print('make tester source=deploy_v1.yaml name=simple_docker')
	print('rm -rf test-no1 && make tester source=deploy_v1.yaml name=no1')

