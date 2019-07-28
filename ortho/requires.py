#!/usr/bin/env python

import subprocess,re
from .bash import bash

def is_terminal_command(name):
	"""
	Check returncode on which.
	"""
	check_which = subprocess.Popen('which %s'%name,shell=True,executable='/bin/bash',
		stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	check_which.communicate()
	return check_which.returncode

def version_number_compare(v1,v2):
	# via https://stackoverflow.com/questions/1714027
    def normalize(v):
        return [int(x) for x in re.sub(r'(\.0+)*$','', v).split(".")]
    # cmp is gone in python 3
    cmp = lambda a,b: (a > b) - (a < b)
    return cmp(normalize(v1),normalize(v2))

def requires_program(*reqs):
	def decorator(function):
		def wrapper(*args,**kwargs):
			for req in reqs:
				return_value = is_terminal_command(req)
				if return_value!=0: 
					raise Exception(('function %s requested a terminal command but we '
						'cannot find %s at the terminal (via `which %s`). '
						'are you sure you are in the right environment?')%(function,req,req))
			result = function(*args,**kwargs)
			return result
		return wrapper
	return decorator

#! deprecated below
def _requires_python_check(req,msg):
	regex_version = '^(.*?)(=|>=|>)(.*?)$'
	op,version = None,0
	if re.match(regex_version,req):
		req,op,version = re.match(regex_version,req).groups()
	try: 
		mod = __import__(req)
	except Exception as e: raise Exception(msg%(req,''))
	if op:
		version_this = mod.__version__
		if (
			(op=='=' and not version_number_compare(version_this,version)==0) or
			(op=='>' and not version_number_compare(version_this,version)>0) or
			(op=='>=' and not version_number_compare(version_this,version)>=0)
			):
			raise Exception(msg%(req,
				' (requested version %s%s but found %s)'%(
					op,version,version_this)))

#! once the following is generic, replace the _requires_python_check
def _version_checkXXX(req,msg,source):
	regex_version = '^(.*?)(=|>=|>)(.*?)$'
	op,version = None,0
	if re.match(regex_version,req):
		req,op,version = re.match(regex_version,req).groups()
	if op:
		version_this = source
		if (
			(op=='=' and not version_number_compare(version_this,version)==0) or
			(op=='>' and not version_number_compare(version_this,version)>0) or
			(op=='>=' and not version_number_compare(version_this,version)>=0)
			):
			raise Exception(msg%(req,
				' (requested version %s%s but found %s)'%(
					op,version,version_this)))

def _requires_python_checkXXX(req,msg):
	try: mod = __import__(req)
	except Exception as e: raise Exception(msg%(req,''))
	if not hasattr(mod,'__version__'):
		raise Exception(msg%(req,' (no __version__ in this module)'))
	_version_check(req,msg,mod.__version__)


def _version_syntax(req,msg):
	regex_version = '^(.*?)(=|>=|>)(.*?)$'
	op,version = None,0
	match = re.match(regex_version,req)
	if match: 
		req,op,version = re.match(regex_version,req).groups()
	return req,op,version

def _version_check(obs,op,version,msg,req):
	version_this = obs
	if (
		(op=='=' and not version_number_compare(version_this,version)==0) or
		(op=='>' and not version_number_compare(version_this,version)>0) or
		(op=='>=' and not version_number_compare(version_this,version)>=0)
		):
		raise Exception(msg%(req,
			' (requested version %s%s but found %s)'%(
				op,version,version_this)))

def requires_program_version(req,msg):
	req,op,version = _version_syntax(req,msg)
	attempts = [req,'%s -v'%req,'%s --version'%req]
	output_fails,exceptions = [],[]
	for attempt in attempts:
		try:
			result = bash(attempt,scroll=False,strict=False,silent=True)
			# concatenate output even if None
			output = result['stderr']
			output = '' if not output else output
			output += result['stdout'] if result['stdout'] else ''
			output_fails.append((attempt,output))
			if result['return']: 
				raise Exception(msg%(attempt,'. cannot locate program "%s"'%req))
			# parse a version number
			match = re.findall('(\d+(?:\.\d+)*)',output)
			if len(match)>1: 
				raise Exception(msg%(attempt,' multiple version strings in output: %s'%str(match)))
			elif len(match)==0: 
				raise Exception(msg%(attempt,' cannot find a version string in the output'))
			else: _version_check(match[0],op,version,msg,req)
			return True
		except Exception as e: 
			exceptions.append(e)
	#! print('error versions are insufficient, see report: %s'%str(output_fails))
	#! cannot raise e here, possibly due to a scope issue
	#! the last 
	print('warning complete list of exceptions is:')
	print('\n'.join([' '*4+str(e) for e in exceptions]))
	raise exceptions[-1]

def requires_python_check(*reqs):
	msg = ('we expect python module "%s"%s. '
		'you may need to point to an environment by running: '
		'make set activate_env="~/path/to/bin/activate env_name"')
	for req in reqs: _requires_python_check(req,msg)

#! note that some of these decorators are somewhat repetitive

def requires_python(*reqs):
	def decorator(function):
		msg = ('function "%s"'%function.__name__+' expects python module "%s"%s. '
			'you may need to point to an environment by running: '
			'make set activate_env="~/path/to/bin/activate env_name"')
		def wrapper(*args,**kwargs):
			for req in reqs: _requires_python_check(req,msg)
			result = function(*args,**kwargs)
			return result
		return wrapper
	return decorator

def requires_version(*reqs):
	def decorator(function):
		msg = ('Function "%s"'%function.__name__+' expects program with version "%s"%s.')
		def wrapper(*args,**kwargs):
			for req in reqs: requires_program_version(req,msg)
			result = function(*args,**kwargs)
			return result
		return wrapper
	return decorator
	
