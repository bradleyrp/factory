#!/usr/bin/env python

"""
All interactions with omnicalc are here.
"""

import os,sys,json,re,subprocess,datetime,glob,pprint
import nbformat as nbf
from django.conf import settings
from django.http import HttpResponse
from .tools import bash

import sys
#---remote imports
sys.path.insert(0,os.path.join(settings.FACTORY,'mill'))
sys.path.insert(0,os.path.join(settings.CALC,'omni','..'))
#! new addition for getting omni below
sys.path.insert(0,os.path.abspath(os.path.join(settings.CALC,'omni','..')))
#! mising from cluster import backrun
#!!! replace cluster and tools with ortho tools?
import omni
from omni.base.store import picturedat
from omni.omnicalc import WorkSpace
#! omnicalc = __import__('omnicalc')

def get_workspace():
	"""
	Get a fresh copy of the workspace. Called by the calculator index function.
	"""
	#---! prefer to set the meta_filter somewhere in the factory?
	work = WorkSpace(cwd=settings.CALC,checkup=True)
	return work

def make_bootstrap_tree(spec,floor=None,level=None):
	"""
	Convert a nested dictionary to dictionary for JSON for bootstrap tree visualization.
	"""
	#---top level gets a number
	if not level: level = 0
	if level and floor and level>=floor: 
		yield({"text":re.sub("'",'\\"',str(spec))})
	else:
		for key,val in spec.items():
			if type(val)==dict: 
				yield({"text":key,"nodes":list(
					make_bootstrap_tree(val,level=level+1,floor=floor))})
			else: 
				#---! general way to handle non-dictionary items
				#---! note the try block is for printing postdat objects
				#---we always set selectable to false because we do not wish to confuse users and
				#---...these trees are really just for viewing data or showing a link to edit something.
				#---...note that unsetting selectable below only stops the events. use colors in base.html to 
				#---...hide the selection
				try: yield {"text":key,'selectable':False,
					"nodes":[{"text":re.sub("'",'\\"',str(val.__dict__))}]}
				except: yield {"text":key,'selectable':False,
					"nodes":[{"text":re.sub("'",'\\"',str(val))}]}

def get_notebook_token():
	"""
	See if there is a notebook server running for the factory.
	"""
	#---check the notebook log file to get the token
	with open('logs/notebook.%s'%settings.NAME) as fp: text = fp.read()
	# note that this token will also match a dummy noticed by the factory run command for using 
	# ... a password instead of the token
	token_regex = r'http:(?:.*?)\:(\d+)(?:\/\?token=)(.*?)\s'
	jupyters_by_port = dict(re.findall(token_regex,text,re.M+re.DOTALL))
	if len(jupyters_by_port)!=1: 
		print(text)
		raise Exception('error figuring out jupyter token: %s. notebook text is:\n%s'%(
			jupyters_by_port,text))
	else: return list(jupyters_by_port.values())[0]

class FactoryBackrun:

	"""
	Run a computation in the background and keep track of the logs.
	"""

	def __init__(self):
		#---several hard-coded parameters for this background-runner
		self.lock_fn = 'pid.%s.compute.lock'%settings.NAME
		self.lock_fn_abs = os.path.join(settings.FACTORY,settings.CALC,self.lock_fn)
		self.cwd = settings.CALC
		self.state = 'idle'
		self.log_fn = None

	def run(self,cmd,log,kill_switch_coda_extras=None,use_bash=False):
		"""
		Generic computation which uses the logging functionality.
		Used for `make compute` and the thumbnailer.
		"""
		self.avail()
		self.log_fn = log
		kwargs = dict(log=self.log_fn,stopper=self.lock_fn_abs,
			cwd=self.cwd,killsig='KILL',scripted=False,kill_switch_coda='rm %s%s'%(self.lock_fn_abs,
				'\n%s'%kill_switch_coda_extras if kill_switch_coda_extras else ''))
		#---single command
		if not use_bash: 
			cmd = '%s kill_switch="%s"'%(cmd,self.lock_fn_abs)
			backrun(cmd=cmd,**kwargs)
		#---bash script
		else: 
			print('USING BASH')
			print(cmd)
			backrun(bash=cmd,**kwargs)
		self.log_fn_abs = os.path.join(self.cwd,self.log_fn)
		self.state = 'running'

	def avail(self):
		"""Make sure we are not running."""
		if self.state!='idle':
			#---! we previously threw an exception here but we tried to 
			#---! ...make it look nice and now it never happens
			return HttpResponse(
				'<h1>warning</h1><br>you must click "reset calculation" on the terminal before '
				'starting another calculation. this ensures that you inspect any previous error '
				'logs before continuing.')

	def dispatch_log(self):
		"""
		Populate a view with variables that descripte the logging state.
		"""
		outgoing = dict()
		outgoing['show_console'] = self.state in ['running','completed']
		if outgoing['show_console']:
			self.read_log()
			outgoing['log_text'] = self.last_log_text
			outgoing['log_status'] = self.state
		return outgoing

	def read_log(self):
		"""Read the log file."""
		try: 
			with open(self.log_fn_abs) as fp: 
				self.last_log_text = fp.read()
		#---if log is missing we must continue with out jamming everything up
		except: pass

	def logstate(self):
		"""
		Describe the logging status for the logging function that interacts with the console.
		Note that the lock file exists when the job is running.
		The backrun function clears the lock file at the end of the run.
		"""
		#---idle returns nothing and tells the logger to redirect to index and close the AJAX calls
		if self.state == 'idle': return None
		#---if we are running we get the text of the log file
		elif self.state == 'running': 
			self.read_log()
			#---if the lock file is missing, we change our state to completed 
			if not os.path.isfile(self.lock_fn_abs): self.state = 'completed'
		#---return the log text
		return {'line':self.last_log_text,'running':self.state in ['running','completed'],
			'calculator_status':self.state}

class PictureAlbum:

	"""
	Manage the factory view of the plots.
	"""

	def __init__(self,backrunner,regenerate_all=False):

		"""Prepare an album of plots. This includes thumbnails."""
		#---check for a thumbnails directory
		thumbnails_subdn = 'thumbnails-factory'
		thumbnails_dn = os.path.join(settings.PLOT,thumbnails_subdn)
		if not os.path.isdir(thumbnails_dn): os.mkdir(thumbnails_dn)
		#---catalog top-level categories
		picture_files = glob.glob(os.path.join(settings.PLOT,'*.png'))
		cats,picture_files_filter = [],[]
		for fn in picture_files:
			try: 
				cats.append(re.match('^fig\.(.*?)\.',os.path.basename(fn)).group(1))
				picture_files_filter.append(fn)
			except: print('[WARNING] wonky picture %s'%fn)
		cats = list(set(cats))

		#---reconstruct the plot_details every time
		plots_details = {}
		#---! other plot formats?
		#---scan for all PNG files
		for fn in picture_files_filter:
			base_fn = os.path.basename(fn)
			details = {'fn':base_fn}
			#---check for thumbnails
			thumbnail_fn = os.path.join(thumbnails_dn,base_fn)
			#---the regenerate_all flag rewrites all thumbnails
			if regenerate_all: details['thumb'] = False
			else: details['thumb'] = os.path.isfile(thumbnail_fn)
			#---construct a minimal descriptor of the plot from the name only
			try: shortname = re.sub('[._]','-',re.match('^fig\.(.*)\.png$',base_fn).group(1))
			except: shortname = re.match('^(.*?)\.png$',base_fn).group(1)
			details['shortname'] = shortname
			try:
				meta_text = picturedat(base_fn,directory=settings.PLOT)
				details['meta'] = pprint.pformat(meta_text,width=80) if meta_text else None
			except: details['meta'] = None
			#---a unique key for HTML elements
			details['ukey'] = re.sub('\.','_',base_fn)
			#---category for showing many pictures at once
			#---! note repetitive with the catalog of top-level categories above
			details['cat'] = re.match('^fig\.(.*?)\.',os.path.basename(base_fn)).group(1)
			plots_details[base_fn] = details

		#---package the data into the global album which gets shipped out to the view
		self.album = dict(files=dict([(k,plots_details[k]) for k in plots_details.keys()[:]]),
			thumbnail_dn_base=thumbnails_subdn,thumbnail_dn_abs=thumbnails_dn,cats=sorted(cats))

		#---make thumbnails if necessary
		if any([v['thumb']==False for k,v in plots_details.items()]): self.thumbnail_maker(backrunner)

	def thumbnail_maker(self,backrunner):
		"""
		Construct a script to make thumbnails.
		"""
		global album
		cwd = settings.CALC
		lines = ['#!/bin/bash']
		thumbnails_dn = self.album['thumbnail_dn_abs']
		for ii,(name,item) in enumerate(self.album['files'].items()):
			print('checking thumb for %s'%name)
			if not item['thumb']:
				source_fn = os.path.join(settings.PLOT,name)
				thumbnail_fn = os.path.join(thumbnails_dn,name)
				lines.append('echo "[STATUS] converting %s"'%os.path.basename(thumbnail_fn))
				lines.append('convert %s -thumbnail 500x500 %s'%(source_fn,thumbnail_fn))
				#---! should we update here assuming that it is made correctly?
				self.album['files'][name]['thumb'] = thumbnail_fn 
		lines.append('echo "[STATUS] thumbnails are complete. hit \'reset calculator\' '+
			'or refresh the page to get the new thumbnails. use the buttons on the '+
			'\'picture selectors\' tile to view the image gallery."')
		lines.extend(['rm -f script-make-thumbnails.sh','rm -f pid.%s.compute.lock'%settings.NAME])
		with open(os.path.join(settings.CALC,'script-make-thumbnails.sh'),'w') as fp:
			fp.write('\n'.join(lines))
		global logging_fn
		logging_fn = os.path.join(settings.FACTORY,settings.CALC,'log-thumbnails')
		backrunner.run(cmd='bash script-make-thumbnails.sh',log='log-thumbnails')

class FactoryWorkspace:

	"""
	Wrap an omnicalc workspace for the factory.
	"""

	def __init__(self):
		"""Hold a copy of the workspace."""
		self.refresh()

	def refresh(self):
		"""Get another copy of the workspace. This reimports all data but does not run a calculation."""
		self.work = WorkSpace(cwd=settings.CALC,checkup=True)
		self.time = datetime.datetime.now()
		# catalog all plots so we know which ones are candidates for conversion to interactive scripts.
		# ... note that a valid plot (for interactive mode) is in the plots dictionary and found on disk
		self.plot_scripts = {}
		for key in self.work.metadata.plots:
			script_fn = self.work.metadata.plots[key].get('script','plot-%s.py'%key)
			if os.path.isfile(os.path.join(settings.CALC,'calcs',script_fn)):
				self.plot_scripts[script_fn] = {'plotname':key,
					'autoplot':self.work.metadata.plots[key].get('autoplot',False)}
		# add stray plots even if they are not in the plots dictionary
		for fn_abs in glob.glob(os.path.join(settings.CALC,'calcs','plot-*.py')):
			fn = os.path.basename(fn_abs)
			if fn not in self.plot_scripts:
				self.plot_scripts[fn] = {'plotname':
					re.match('^plot-(.+)\.py$',os.path.basename(fn)).group(1)}

	def clear_stale(self):
		try: bash('make clear_stale',cwd=settings.CALC)
		except: pass

	def meta_changed(self):
		"""Check meta files for changes so you can tell the user a refresh may be in order."""
		#---! removed for compatibility with omnicalc development branch
		return False
		mtimes = [os.path.getmtime(i) for i in self.work.specs_files]
		found_meta_changes = any([self.time<datetime.datetime.fromtimestamp(os.path.getmtime(i)) 
			for i in self.work.specs_files])
		return found_meta_changes

	def timestamp(self):
		"""Return the timestamp of the latest refresh."""
		return self.time.strftime('%Y.%m.%d %H:%M.%S')
