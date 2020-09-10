#!/usr/bin/env python

import yaml
import ortho

def yaml_do_select(what,name=None,debug=False,**kwargs):
	"""
	This function executes a portion of a YAML file.
	We moved it outside of the cli.py Interface(Parser) object to generalize
	it further and allow other command-line arguments.
	"""
	#!!! issue: incorrect kwargs are routed into yaml and there is no warning
	#!!!   that they are invalid. this is an inherent downside possibly
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
			def cli_hook(loader,data):
				"""
				This hook connects the CLI via kwargs to the YAML file.

				This yaml_do_select function is typically run with 
				`make do <target.yaml> <name>` from the factory. If you need to
				hook this up to the command line, but wish to simply run the
				yaml file with all of the tags, you can use the !cli tag to add
				a value from a kwargs key to the yaml document. To connect this
				to the CLI, you can use `make use specs/cli_<name>.yaml` to
				add a command with unstructured arguments, and then this command
				can pass these along to yaml_do_select kwargs. In short, this
				hook allows you to run a stock yaml file with tags that point
				to other codes while also populating variables directly from
				the command line. The only mediator is the CLI function which
				must be registered in config.json with a `make use` call.
				"""
				# two arguments imply a key and a default
				if isinstance(data.value,list)==1:
					if len(data.value)==2:
						key,default = [i.value for i in data.value]
						return kwargs.get(key,default)
					elif len(data.value)==1:
						key = kwargs[data.value[0].value]
						return kwargs[key]
					else: raise ValueError
				# if not a list, then a string and we return the value
				return kwargs[data.value]
			# add the constructor here and load will end the execution
			yaml.add_constructor("!select",constructor)
			yaml.add_constructor("!cli",cli_hook)
			# EXECUTE the yaml here
			spec = yaml.load(text,Loader=yaml.Loader)
			if debug:
				# note that we may wish to manipulate objects after the yaml
				#! document this option
				import code
				code.interact(local=spec,
					banner='[INTERACT] welcome to YAML land')
	# standard execution
	else: 
		spec = yaml.load(text,Loader=yaml.Loader)
		# after checking collisions above we pass name through
		if name: spec['name'] = name
		#! previously tried to add **kwargs from do to spec['kwargs']
		Action(**spec).solve
