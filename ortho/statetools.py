#!/usr/bin/env python

# Python 2/3 compatabilty and color printer
from __future__ import print_function
from __future__ import unicode_literals

__doc__ = """
statetools.py

Tools for parsing the CLI, managing a cache file and distributing it to other
classes. Developed for Community Collections.

Development note: this could be parted out to the appropriate ortho submodules.
"""

import os
import sys
import re
import argparse
import json
import time
import datetime
import copy
import traceback

from .handler import introspect_function
from .misc import str_types,say
from .dev import tracebacker

class Singleton(type):
	# via https://stackoverflow.com/a/42239713
	#! use with `__metaclass__ = Singleton` however this fails
	def __init__(cls, name, bases, dict):
		super(Singleton, cls).__init__(name, bases, dict)
		cls._instance = None
	def __call__(cls, *args, **kw):
		if cls._instance is None:
			cls._instance = super(Singleton, cls).__call__(*args, **kw)
		return cls._instance

class Cacher(object):
	"""
	Class decorator which supplies a cache and associated functions.
	Note that the child class needs to run a try/except like this one:
	To write the cache on failure or success use self._try_except or
	alternately self._try_else otherwise the cache is not saved!
	"""
	def __init__(
		self,
		# default policies
		cache=None,
		cache_fn='cache.dat',
		closer=None,
		cache_policy='standard',
		errorclear_policy='clear',
		establish_policy='check',
			reserve_policy=True):
		if not isinstance(cache_fn,str_types):
			raise Exception((
				'The argument to Cacher must be a string, '
				'the name of the cache file. Use `Cacher()` for the '
				'default. We received cache_fn=%s in error.')%cache_fn)
		# allow the user to pass along a cache
		self.cache = cache
		# hooks
		self.closer = closer
		# pass the decorator settings to the CachedClass below
		self.cache_fn = cache_fn
		self.cache_policy = cache_policy
		self.errorclear_policy = errorclear_policy
		self.establish_policy = establish_policy
		self.reserve_policy = reserve_policy

	def __call__(self, cls):
		# when using a class decorator is that the derived class is a singleton
		class CachedClass(cls):
			# receive the cache_fn from the decoration
			# clumsy variable passing below
			cache = self.cache
			cache_fn = self.cache_fn
			cache_policy = self.cache_policy
			cache_policy = self.cache_policy
			errorclear_policy = self.errorclear_policy
			establish_policy = self.establish_policy
			reserve_policy = self.reserve_policy
			closer = self.closer

			def __init__(self):
				if self.cache is None:
					self.cache = {}
				# an empty cache policy means we do not use it
				if self.cache_policy == 'empty':
					return
				# load
				if not os.path.isfile(self.cache_fn):
					pass
				else:
					print('status reading %s'%self.cache_fn)
					with open(self.cache_fn) as fp:
						incoming = json.load(fp)
						# avoid collisions here?
						self.cache.update(**incoming)
				if self.reserve_policy:
					self.cache_copy = copy.deepcopy(self.cache)
				self.errorclear()
				# initialize the parent class
				print('status done reading cache')
				super(cls,self).__init__()

			def _try_except(self, exception=None):
				# the languish flag turns off the Cacher
				if self.cache.get('languish',False):
					return
				if self.cache_policy != 'empty':
					self.cache['error'] = str(exception)
				self._standard_write()
				if exception is not None:
					# suppress exceptions if requested
					if not self.cache.pop('traceback_off',False):
						tracebacker(exception)
				else:
					raise Exception('caught exception but it was not passed')

			def _try_else(self):
				# the languish flag turns off the Cacher
				if self.cache.get('languish',False):
					return
				# apply the hooks before write
				# hooks are not used on _try_except above for debugging
				if self.closer:
					self.closer()
				self._standard_write()

			def _standard_write(self):
				if self.cache_policy == 'standard':
					if self.reserve_policy:
						if self.cache == self.cache_copy:
							print('status cache is unchanged')
							return
					# standard write
					print('status writing %s' % self.cache_fn)
					with open(self.cache_fn,'w') as fp:
						json.dump(self.cache,fp)
				elif self.cache_policy == 'empty':
					pass
				else:
					raise Exception('invalid cache policy: %s'%
						self.cache_policy)

			def errorclear(self):
				if self.errorclear_policy == 'clear':
					if 'error' in self.cache:
						del self.cache['error']
				else:
					raise Exception('invalid errorclear_policy: %s'%
						self.errorclear_policy)

			def establish(self,name,function,**kwargs):
				"""
				Ensure that a result is stored in the cache.
				"""
				if self.establish_policy == 'check':
					if name not in self.cache:
						self.cache[name] = function(**kwargs)
				else:
					# raise Exception('invalid policy %s' % policy)
					raise Exception('invalid policy')
		return CachedClass

def logger(cache):
	"""Decorator for updating the cache when a function runs."""
	if not isinstance(cache,dict):
		raise Exception((
			'The @logger decorator must have '
			'the cache as an argument. We received: %s')%str(cache))

	def intermediate(function):
		def logger(*args, **kwargs):
			if 'log' not in cache:
				cache['log'] = []
			ts = datetime.datetime.fromtimestamp(
				time.time()).strftime('%Y.%m.%d.%H%M')
			record = {'when':ts,'function_name':function.__name__}
			#! we do not save the answer
			result = function(*args,**kwargs)
			# record['return'] = result
			cache['log'].append(record)
			return result
		return logger
	return intermediate

class Parser:
	"""
	Convert all methods in a subclass into argparse and run with cacher.
	Note that you cannot use arbitrary parameters via **kwargs.
	"""
	__metaclass__ = Singleton
	# protected functions from Cacher hidden from argparse
	protected_functions = ['closer','errorclear','establish']
	parser_order = False
	# hooks for special instructions from a subclass or free functions
	subcommander = []
	free_functions = []

	def _preproc(self):
		"""
		Convert alternate syntax key=val to --key val. The former is used
		by the makefile interface. When this function runs, we clean up
		the sys.argv so that either make or the direct interface can be used
		in exactly the same way. This is nondestructive to sys.argv because
		Parser is a singleton. Note that you still cannot use --key val with
		make but otherwise the make and direct syntax are identical.
		"""
		regex_alt = '^(?:--)?(.+)=(.+)$'
		revised = []
		for item in sys.argv:
			match = re.match(regex_alt,item)
			if match:
				revised.append('--%s'%match.group(1))
				revised.append(match.group(2))
			# special handling for the 'help' keyword
			elif item=='help':
				revised.append('-h')
			else: revised.append(item)
		sys.argv = revised

	def _get_function(self,name):
		"""Look up a function locally or from an extension."""
		if name in self.specials: func = self.specials[name]
		else: func = getattr(self,name)
		return func

	def _function_to_subcommand(self,name):
		"""
		Convert a subcommand to an argparse function.
		"""
		func = self._get_function(name)
		detail = {}
		if hasattr(func, '__doc__'):
			detail['help'] = func.__doc__
		sub = self.subparsers.add_parser(name,**detail)
		# introspection
		inspected = introspect_function(func,check_varargs=True)
		if inspected.get('*') or inspected.get('**'):
			raise Exception(
				'cannot use arbitrary arguments in Parser method: %s'%name)
		if ('func' in inspected['args']
				or 'func' in inspected['kwargs']):
			raise Exception('cannot use the argument func in %s'%name)
		# temporary fix for introspect_function issue
		if (sys.version_info < (3,3) and len(inspected['args']) > 0
				and inspected['args'][0] == 'self'):
			inspected['args'] = inspected['args'][1:]
		for arg in inspected['args']:
			sub.add_argument(arg)
		for arg in inspected['kwargs'].keys():
			val = inspected['kwargs'][arg]
			if isinstance(val,bool):
				if val:
					sub.add_argument('--no-%s'%arg,dest=arg,
						action='store_false')
				else:
					sub.add_argument('--%s'%arg,dest=arg,
						action='store_true')
				sub.set_defaults(**{arg:val})
			# we treat the None as if it is expecting an argument
			#   so that you can use None to rely on default kwargs
			elif isinstance(val, str_types) or isinstance(val, type(None)):
				sub.add_argument('--%s'%arg,
					dest=arg,default=val,type=str,
					help='Default for "%s": "%s".' %
					(arg,str(val)))
			elif isinstance(val, int):
				sub.add_argument('--%s'%arg,
					dest=arg,default=int(val),type=int,
					help='Default for "%s": "%s".'%
					(arg,int(val)))
			else:
				# development error if you use an invalid type in a parser
				raise Exception((
					'cannot automatically make a parser '
					'from argument to "%s": "%s" (default "%s")')%(
					name,arg,str(val)))
		# set the function
		sub.set_defaults(func=func)

	def _call_free_function_tail(self):
		"""
		Free function with a 'tail' with any syntax. 
		This feature is marked by avoiding kwargs and annotating the last 
		argument with the 'tail' string.
		"""
		raise Exception('dev')

	def _call_free_function(self):
		"""
		Call a function with arbitrary parameters
		This function recovers the ortho.cli functionality.
		"""
		print("status calling a function with arbitrary arguments")
		call_script,name,tail = sys.argv[0],sys.argv[1],sys.argv[2:]
		#!!! disabled during testing:
		#!!!   if call_script!='cli.py': 
		#!!!	raise Exception('arrived here from unknown')
		func = self._get_function(name)
		# we inspect the function again but we could have saved it earlier
		inspected = introspect_function(func,check_varargs=True)
		if hasattr(func,'__doc__') and '-h' in sys.argv:
			print('status instructions follow:\n')
			print('\n'.join(['  %s'%i for i in func.__doc__.splitlines()]))
		sub = self.subparsers.add_parser(name)
		#! sub.add_argument('subcommand')
		# leave early if we are looking for help to prevent confusing notes
		#!!! if '-h' in sys.argv: return
		# build the parser from the args: this trick allows arbitrary args
		known_args,unknown = self.parser.parse_known_args()
		obs_known_args = vars(known_args)
		if obs_known_args: 
			# known_args are not added to parser so we catch them here
			raise Exception('preemptively got some args: %s'%obs_known_args)
		# step 1: identify keyword arguments with values from the list
		inds_kwargs_val = [(ii,ii+1) for ii,i in enumerate(unknown) 
			if i.startswith(('-','--')) 
			and ii<len(unknown)-1 
			and not unknown[ii+1].startswith(('-','--'))]
		# step 2: identify lone kwargs which must be booleans
		inds_kwargs_bool = [(ii,) for ii,i in enumerate(unknown) 
			if i.startswith(('-','--')) 
			and ii==len(unknown)-1 or (ii<len(unknown)-1 
			and unknown[ii+1].startswith(('-','--')))]
		# step 3: the remainder are arguments
		inds_args = [i for i in range(len(unknown)) if i not in [m 
			for n in inds_kwargs_bool+inds_kwargs_val for m in n]]
		# if we have star arguments in the signature then args go there
		if inspected.get('*'):
			sub.add_argument('args',nargs='*')
		else:
			raise Exception('dev: named arguments')
		# keyword arguments
		for ind_name,ind_val in inds_kwargs_val:
			sub.add_argument(unknown[ind_name],default=unknown[ind_val])
		# keyword booleans
		for ind_bool in inds_kwargs_bool:
			arg = unknown[ind_bool[0]]
			#! see sub.print_help() for why these fail
			if 0:
				sub.add_argument('--%s'%arg,action='store_true')
				sub.add_argument('--no-%s'%arg,action='store_false')
			#! no ability to do the --no-X thing yet
			sub.add_argument(arg,action='store_true')
		# set the function name
		sub.set_defaults(func=func)
		# check unknown
		known,unknown = sub.parse_known_args()
		if unknown: raise Exception(
			'failure to process arguments: %s'%str(unknown))
		# connect the function to the parser
		sub.set_defaults(func=func)
		# now that we have prepared the parser we add the function and call
		args = self.parser.parse_args()
		self._call_free(incoming=args)

	def __init__(self, parser_order=None):
		subcommand_names = [
			func for func in dir(self)
			if callable(getattr(self,func))
			# hide functions with underscores and ignore a closer for Cacher
			and not func.startswith('_')
			and not func in self.protected_functions]
		# preprocess the arguments
		self._preproc()
		#! need a custom ordering here
		if self.parser_order:
			subcommand_names = (
				[i for i in subcommand_names if i in parser_order] +
				[i for i in subcommand_names if i not in parser_order])
		self.parser = argparse.ArgumentParser(
			description='Community Collections Manager.')
		self.subparsers = self.parser.add_subparsers(
			title='subcommands',
			description='Valid subcommands:',
			help='Use the help flag (-h) for more details on each subcommand.')
		# the subcommander list points to external functions
		self.specials = {}
		if self.subcommander:
			from .imports import importer
			for name,target in self.subcommander.items():
				try: 
					mod_target,func_name = re.match(
						r'^(.+)\.(.*?)$',target).groups()
					self.specials[name] = importer(mod_target)[func_name]
				except Exception as e:
					raise Exception('cannot import %s from %s'%(
						func_name,mod_target))
		collide_special = [i for i in self.specials if i in subcommand_names]
		if any(collide_special):
			raise Exception(
				'special CLI function collisions: %s'%collide_special)
		# loop over subcommands excluding specials
		for name in subcommand_names:
			self._function_to_subcommand(name)
		for name in self.specials.keys():
			# check if special functions have arbitrary arguments
			func = self._get_function(name)
			inspected = introspect_function(func,check_varargs=True)
			# if we find the star then it has variable arguments
			if inspected.get('*') or inspected.get('**'):
				detail = {}
				if hasattr(func, '__doc__'):
					detail['help'] = func.__doc__
				sub = self.subparsers.add_parser(name,**detail)
				self.free_functions.append(name)
			else: self._function_to_subcommand(name)
		# divert free functions here (note sys.argv[0]=='cli.py')
		if len(sys.argv)>1 and sys.argv[1] in self.free_functions:
			self._call_free_function()
			return
		# if we have a standard function we continue with argparse
		args = self.parser.parse_args()
		# print help if no function
		if not hasattr(args,'func'):
			self.parser.print_help()
		# separate Cacher methods before execute
		else:
			# we protect the main execution loop with a handler here
			try: self._call(args)
			except Exception as e:
				#! sometimes traceback is missing, but after adding this
				#!   we sometimes get a double error
				#! removed: tracebacker(e)
				# traceback is necessary here or raise is not useful
				if hasattr(self,'_try_except'): 
					self._try_except(exception=e)
			else: 
				if hasattr(self,'_try_else'): 
					self._try_else()
		return

	def _call(self,args):
		"""Main execution loop for a subcommand with handler and else"""
		func = args.func
		delattr(args,'func')
		func(**vars(args))

	def _call_free(self,incoming):
		"""Custom caller for arbitrary functions."""
		args = vars(incoming)
		func = args['func']
		kwargs = dict([(i,j) for i,j in args.items()
			if i not in ('func','args')])
		args = args.get('args',())
		func(*args,**kwargs)

	def debug(self):
		"""
		Use an interactive mode to debug the program.
		"""
		#! note that this function can receive a pipe 
		#!   for example: echo "print(1)" | make debug
		import code
		sys.ps1 = "[cc] >>> "
		vars = globals()
		vars.update(locals())
		if hasattr(self, 'subshell',):
			vars.update(**self.subshell)
		import readline
		import rlcompleter
		readline.set_completer(rlcompleter.Completer(vars).complete)
		readline.parse_and_bind("tab: complete")
		code.interact(local=vars,banner='')

class Convey(object):
	"""
	Class decorator which supplies a cache and associated functions.
	"""
	def __init__(self, **kwargs):
		for key, val in kwargs.items():
			setattr(self,key,val)
		self._keys = kwargs.keys()

	def __call__(self, cls):
		# when using a class decorator is that the derived class is a singleton
		class Convey(cls):
			for key in self._keys:
				setattr(cls, key, getattr(self, key))
		Convey.__name__ = cls.__name__
		return Convey

class StateDict(dict):
	"""
	Special dictionary for watching what happens to the state.
	Prototype only.
	"""
	def __init__(self,debug=False,*args,**kwargs):
		self._debug = debug
		super(StateDict,self).__init__(*args,**kwargs)
		import ipdb;ipdb.set_trace()

	def _get_line(self):
		"""Get the line that brought you here."""
		# does not work on python 2
		if sys.version_info<(3,0): return
		try: raise Exception('introspection-exception')
		except:
			stack = traceback.extract_stack()
			# the choice of 3 is probably static
			# note that if the line does not have state or self.cache
			#   in it, this might be earlier in the broken line
			#   because the stack line does not read to the true abstract
			#   beginning of the line
			#! disabled because uninformative
			if 0:
				where = stack[-3]
				print('debug we are in %s lineno %d line: `%s`'%(
					where.filename, where.lineno, where.line))
		return

	def _say(self,x): return say(x,'mag_gray')

	def get(self,x,d=None):
		if self._debug:
			print('debug state get "%s"'%self._say(x))
			self._get_line()
		return super(StateDict, self).get(x,d)

	def __getitem__(self,x):
		if self._debug:
			print('debug state get "%s"'%self._say(x))
			self._get_line()
		return super(StateDict,self).__getitem__(x)

	def set(self,x,y):
		if self._debug:
			print('debug state set "%s" "%s"'%(self._say(x),self._say(y)))
			self._get_line()
		return super(StateDict,self).set(x,y)

	def __setitem__(self,x,y):
		if self._debug:
			print('debug state set "%s" "%s"'%(self._say(x),self._say(y)))
			self._get_line()
		return super(StateDict, self).__setitem__(x,y)
