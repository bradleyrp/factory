#!/usr/bin/env python
# testing from a subdirectory
import sys,os;sys.path.insert(0,os.getcwd())
# USAGE: python lib/tests/statetools_parser_tests.py
import ortho
def ext1(*args,**kwargs):
	"""Function with arbitrary arguments."""
	print((args,kwargs))
def ext2(a,*args,**kwargs):
	"""Function with arbitrary arguments."""
	print((args,kwargs,'a=%s type %s'%(str(a),type(a))))
def ext3(*args,a=False,**kwargs):
	"""Function with arbitrary arguments."""
	print((args,kwargs,'a=%s type %s'%(str(a),type(a))))
def ext4(*args,a,**kwargs):
	"""Function with arbitrary arguments."""
	print((args,kwargs,'a=%s type %s'%(str(a),type(a))))
class Interface(ortho.Parser):
	subcommander = {}
	for key in ['ext1','ext2','ext3','ext4']:
		subcommander[key] = '%s.%s'%(__file__,key)
	#! you cannot have *args,**kwargs inside the Parser
	def t01(self,a): print(a)
	def t02(self,a,b=1): print(a,b)
	def t03(self,b=1): print(b)
	def t05(self,a,b,c,sure=True):
		print(self._via_makeface)
		print((a,b,c,sure))
if __name__=='__main__':
	Interface()