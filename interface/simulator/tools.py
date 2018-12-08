#!/usr/bin/env python

import os,sys,subprocess,re,json

def bash(command,log=None,cwd=None,inpipe=None,catch=False):
	"""
	Run a bash command
	"""
	if not cwd: cwd = './'
	if log == None: 
		if inpipe: raise Exception('under development')
		kwargs = dict(cwd=cwd,shell=True,executable='/bin/bash')
		if catch: kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE)
		proc = subprocess.Popen(command,**kwargs)
		stdout,stderr = proc.communicate()
	else:
		#---if the log is not in cwd we see if it is accessible from the calling directory
		if not os.path.isdir(os.path.dirname(os.path.join(cwd,log))): 
			output = open(os.path.join(os.getcwd(),log),'w')
		else: output = open(os.path.join(cwd,log),'w')
		kwargs = dict(cwd=cwd,shell=True,executable='/bin/bash',
			stdout=output,stderr=output)
		if inpipe: kwargs['stdin'] = subprocess.PIPE
		proc = subprocess.Popen(command,**kwargs)
		if not inpipe: stdout,stderr = proc.communicate()
		else: stdout,stderr = proc.communicate(input=inpipe)
	if stderr: raise Exception('[ERROR] bash returned error state: %s'%stderr)
	if proc.returncode: 
		if log: raise Exception('[ERROR] bash error, see %s'%log)
		else: 
			extra = '\n'.join([i for i in [stdout,stderr] if i])
			raise Exception('[ERROR] bash error'+(': '+extra if extra else ''))
	return {'stdout':stdout,'stderr':stderr}

def strip_builtins(obj):
	"""Remove builtins from a hash in place."""
	#---! whoa this is weird! we wish to collect functions without preventing them from printing...
	if '__all__' in obj.keys(): keys = obj['__all__']
	else: keys = [key for key in obj.keys() if not key.startswith('__')]
	#---! 
	hidden = obj.pop('_not_all',[])
	for h in hidden:
		if h not in keys: raise Exception('_not_all asks to hide %s but it is absent'%h)
		keys.remove(h)
	if '_not_all' in keys: keys.remove('_not_all')
	#---if you pop __builtins__ here then the imported functions cannot do essentials e.g. print
	#---...so instead we pass along a copy
	return dict([(key,obj[key]) for key in keys])

def import_remote(script,is_script=False,verbose=False):
	"""
	Import a script as a module, directly, iff it is not in the path.
	"""
	dn,fn = os.path.dirname(script),os.path.basename(script)
	assert is_script or os.path.isdir(dn),'cannot find directory "%s" for script %s'%(dn,script)
	#assert os.path.isfile(script),'cannot find file "%s"'%fn
	dn_abs = os.path.join(os.getcwd(),dn)
	assert dn_abs not in sys.path,'found "%s" in sys.path already'%dn_abs
	paths = list(sys.path)
	#---prevent modification of paths while we import
	#---! after moving makeface to the runner directory, we loose the '' at the beginning of sys.path
	#---! ...note that running ipdb's set_trace adds it, so the imports work during debugging, but not runtime
	sys.path.insert(0,dn_abs)
	sys.path.insert(0,'')
	if verbose: print('[NOTE] remotely importing %s'%script)
	#---removed tracebacker from the automacs runner.makeface version of this function
	mod = __import__(os.path.splitext(fn)[0])
	sys.path = paths
	return strip_builtins(mod.__dict__)

def jsonify(text): 
	"""
	Convert python to JSON by replacing single quotes with double quotes and stripping trailing commas
	Note that this checker might be oversensitive if additional JSON errors with the nested dictionary
	Used before SafeDictHook to check for redundant keys. We use a placeholder in block text because JSON 
	cannot process it and the point of this function is to use SafeDictHook to prevent redundant keys.
	"""
	#---remove comments because they might screw up the JSON
	text = re.sub(r'([\"]{3}.*?[\"]{3})','"REMOVED_BLOCK_COMMENT"',text,flags=re.M+re.DOTALL)
	#---note that this fails if you use hashes inside of dictionary values
	text = re.sub(r'(#.*?)\n','',text,flags=re.M+re.DOTALL)
	#---strip trailing commas because they violate JSON rules
	text = re.sub(r",[ \t\r\n]*([}\]])",r"\1",text.replace("'","\""))
	#---fix the case on all booleans
	text = re.sub("True","true",text)
	text = re.sub("False","false",text)
	text = re.sub("None","null",text)
	text = re.sub('\n\s*\n','\n',text,re.M)
	#---! rpb is worried that this is a hack
	return text

def check_repeated_keys(text,verbose=False):
	"""
	Confirm that dict literals pass through non-redundant json checker.
	"""
	extra_msg = "either fix the repeated keys or check for JSON problems."
	text_json = jsonify(text)
	try: _ = json.loads(text_json,object_pairs_hook=SafeDictHook)
	except Exception as e: 
		print('[ERROR] found repeated keys (or JSON encoding error). '+extra_msg)
		if verbose: 
			text_with_linenos = '\n'.join(['[DEBUG]%s|%s'%(str(ll).rjust(4),l) 
				for ll,l in enumerate(text_json.splitlines())])
			print('[ERROR] the following string has a JSON problem:\n'+text_with_linenos)
			print('[ERROR] exception is %s'%e)
			print('[NOTE] repeated key problem!')
		return False
	return True

class SafeDictHook(dict):
	"""
	Hook for json.loads object_pairs_hook to catch repeated keys.
	"""
	def __init__(self,*args,**kwargs):
		self.__class__ == dict
		if len(args)>1: raise Exception('development failure')
		keys = [i[0] for i in args[0]]
		if len(keys)!=len(set(keys)): 
			raise Exception(controlmsg['json']+' PROBLEM KEYS MIGHT BE: %s'%str(keys))
		self.update(*args,**kwargs)

def yamlb(text,style=None,ignore_json=False):
	"""
	Basic parser which reads elegantly-formatted settings blocks (in a manner similar to YAML).
	Development note: missing colons are hard to troubleshoot. Predict them?
	Development note: doesn't prevent errors with multiple keys in a dictionary!
	"""
	unpacked,compacts = {},{}
	str_types = [str,unicode] if sys.version_info<(3,0) else [str]
	#---evaluate code blocks first
	regex_block_standard = r"^\s*([^\n]*?)\s*(?:\s*:\s*\|)\s*([^\n]*?)\n(\s+)(.*?)\n(?!\3)"
	regex_block_tabbed = r"^\s*([^\n]*?)\s*(?:\s*:\s*\|)\s*\n(.*?)\n(?!\t)"
	if style == 'tabbed': regex_block = regex_block_tabbed
	else: regex_block = regex_block_standard
	regex_line = r"^\s*(.*?)\s*(?:\s*:\s*)\s*(.+)$"
	#---strip comments first 
	text = re.sub("\s*#.*?$",'',text,flags=re.M)
	while True:
		blockoff = re.search(regex_block,text,re.M+re.DOTALL)
		if not blockoff: break
		if style == 'tabbed': key,block = blockoff.groups()[:2]
		else: 
			#---collect the key, indentation for replacement, and value
			key,indent,block = blockoff.group(1),blockoff.group(3),''.join(blockoff.groups()[1:])
		#---alternate style does multiline blocks with a single tab character
		#---! who uses this? only vmdmake? might be worth dropping
		if style == 'tabbed': compact = re.sub("(\n\t)",r'\n',block.lstrip('\t'),re.M)
		#---remove indentations and newlines (default)
		else: compact = re.sub('\n','',re.sub(indent,'',block))
		key_under = re.sub(' ','_',key)
		if key_under in unpacked and not ignore_json:
			raise Exception('\n[ERROR] key is repeated in the settings: "%s"'%key)
		unpacked[key_under] = compact
		#---remove the block
		text,count = re.subn(re.escape(text[slice(*blockoff.span())]),'',text)
		if not ignore_json and count>1:
			raise Exception('\n[ERROR] key is repeated in the settings: "%s"'%key)
	while True:
		line = re.search(regex_line,text,re.M)
		if not line: break
		key,val = line.groups()
		key_under = re.sub(' ','_',key)
		if key_under in unpacked and not ignore_json:
			raise Exception('\n[ERROR] key is repeated in the settings: "%s"'%key)
		unpacked[key_under] = val
		text,count = re.subn(re.escape(text[slice(*line.span())]),'',text)
		if not ignore_json and count>1:
			raise Exception('\n[ERROR] key is repeated in the settings: "%s"'%key)
	#---evaluate rules to process the results
	for key,val_raw in unpacked.items():
		#---store according to evaluation rules
		try: val = eval(val_raw)
		except SyntaxError as e:
			#---use of the explicit dict constructor catches repeated keywords
			if e.msg=='keyword argument repeated': 
				raise Exception('keyword argument repeated in: "%s"'%val_raw)
			else: val = val_raw
		except: val = val_raw
		#---protect against sending e.g. "all" as a string and evaluating to builtin all function
		if val.__class__.__name__=='builtin_function_or_method': result = str(val_raw)
		elif type(val)==list: result = val
		elif type(val)==dict:
			if not ignore_json and not check_repeated_keys(val_raw):
				raise Exception('repeated key problem problem was found in: "%s"'%val_raw)
			result = val
		elif type(val) in str_types:
			if re.match('^(T|t)rue$',val): result = True
			elif re.match('^(F|f)alse$',val): result = False
			#---! may be redundant with the eval command above
			elif re.match('^[0-9]+$',val): result = int(val)
			elif re.match('^[0-9]*\.[0-9]*$',val): result = float(val)
			else: result = val
		else: result = val
		unpacked[key] = result
	if False:
		#---unpack all leafs in the tree, see if any use pathfinder syntax, and replace the paths
		ununpacked = [(i,j) for i,j in catalog(unpacked) if type(j)==str and re.match('^@',j)]
		for route,value in ununpacked:
			#---imports are circular so we put this here
			new_value = get_path_to_module(value)
			delveset(unpacked,*route,value=new_value)
	return unpacked
