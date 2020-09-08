#!/usr/bin/env python

import yaml
import ortho

def yaml_do_select(what,name=None,debug=False,**kwargs):
	"""
	This function executes a portion of a YAML file.
	We moved it outside of the cli.py Interface(Parser) object to generalize
	it further and allow other command-line arguments.
	"""
	with open(what) as fp: text = fp.read()
	from lib.yaml_mods import YAMLTagIgnorer,YAMLTagCat
	# the YAMLTagIgnorer decorates a placeholder tree with _has_tag
	spec = yaml.load(text,Loader=YAMLTagIgnorer)
	# special keyword passes through but we protect against collisions
	if 'name' in spec.keys():
		raise Exception('key collision: `make do` cannot use name '
			'in the target spec')
	# detect any tags
	tagged = any(route[-1]=='_has_tag' and val==True 
		for route,val in ortho.catalog(spec))
	# note that we could add some kind of protection here
	# the tagged execution basically just runs the stock yaml file
	#   and allows you to use it as an interface to other codes
	#   with tags that trigger this execution. inside this option
	#   we offer a select option to whittle things down, but otherwise
	#   you should use standard execution in which the dict is sent
	#   to a Handler or you should just use a custom function other
	#   than this "do" function. clearly there are many ways to execute
	if tagged:
		# check for the !select tag which triggers nullification of 
		#   other tags that lie outside of our selection
		raw = yaml.load(text,Loader=YAMLTagCat)
		cat = list(ortho.catalog(raw))
		tags_found = [(path[-2],val) for path,val in cat
			if path[-1]=='_tag_name']
		# standard execution of yaml tags
		if '!select' not in list(zip(*tags_found))[1]:
			if name:
				raise Exception('use of name requires !select tags')
			# EXECUTE the yaml here
			spec = yaml.load(text,Loader=yaml.Loader)
			if debug: 
				#! cleaner option is needed here
				#! only works with ./fac --debug
				try: import ipdb as debugger
				except: import pdb as debugger
				debugger.set_trace()
				#! fix this. rescue self.debug()
				#! consider running this: Action(**spec).solve
			print('status finished with YAML spec')
		# select method in which we only execute yaml tags by selection
		else:
			if not name: 
				raise Exception('found !select but no '
					'name argument came from the command')
			# check to be sure we have exactly one !select in this 
			#   yaml document and also get the key so we can find
			#   valid names for the call
			select_keys = [key[-2] for key,val in cat if val=='!select']
			if len(select_keys)==0:
				# possibly redundant with the check above
				raise Exception('no !select tag')
			elif len(select_keys)>1:
				# could possibly merge them but this is too unstructured
				raise Exception(
					'found multiple !select tags in %s'%what)
			select_key_name = select_keys[0]
			names = [i for i in raw[select_key_name].keys() 
				if i!='_tag_name'] 
			if name not in names:
				raise Exception(('target %s only accepts '
					'the following selections: %s')%(what,str(names)))
			# we prevent code outside of the select loop to ensure
			#   that the user does not sneak in any unintended side
			#   effects that might also run alongside our code however
			#   it might be better to ignore these
			if raw.keys()>set(select_keys):
				raise Exception('when using make-do-select everything '
					'must be subordinate to the select tag')
			# build a custom constructor to selectively execute target
			def constructor(loader,data):
				# recurse only on mappings
				if data.id=='mapping':
					# find the mapping values that correspond to the 
					#   name from the CLI call. note that each node
					#   is a scalar node (a key) and a value
					# we trim the values that do not correspond to the
					#   name. there could be multiple keys with the
					#   same name in our tree, which is interesting but
					#   not really a problem
					dive_inds = [ii for ii,(i,j) 
						in enumerate(data.value) if i.value==name ]
					data.value = [i for ii,i 
						in enumerate(data.value) if ii in dive_inds]
					mapping = loader.construct_mapping(data)
				# ignore non-mappings because we are trying to run code
				else: pass
				return mapping
			# add the constructor here and load will end the execution
			yaml.add_constructor("!select",constructor)
			# EXECUTE the yaml here
			spec = yaml.load(text,Loader=yaml.Loader)
	# standard execution
	else: 
		spec = yaml.load(text,Loader=yaml.Loader)
		# after checking collisions above we pass name through
		if name: spec['name'] = name
		#! previously tried to add **kwargs from do to spec['kwargs']
		Action(**spec).solve
