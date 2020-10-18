#!/usr/bin/env python

import yaml
from .data import catalog

class YAMLObjectInit(yaml.YAMLObject):
    """
    Ensure yaml.YAMLObject subclasses run the constructor. 
    See open issue: https://github.com/yaml/pyyaml/issues/216
    Note that you will have to manually set all of the variables in the
    constructor. 
    """
    @classmethod
    def from_yaml(cls, loader, node):
        """
        Override the usual method so the cls constructor is called.
        You have to manually map the items onto the object however.
        """
        arg_dict = loader.construct_mapping(node, deep=True)
        return cls(**arg_dict)

# note that the YAMLTagIgnorer and specifically YAMLTagCat were moved here
#   from lib/yaml_mods.py and were only being used at the time by 
#   the make-do-select feature in yaml_run. the multi_constructor is the
#   method for applying the specific ignorer or catalog feature to the loader
#   but they should not touch other yaml features in the meantime

class YAMLTagIgnorer(yaml.SafeLoader):
    """
    Detect yaml recipes with Tags. Works with the constructor below.
    """
    def check_tags(self,suffix,node):
        # return a placeholder that notes tags later checked recursively
        return {'_has_tag':True}

# the YAMLTagIgnorer is constructed on any tag.
YAMLTagIgnorer.add_multi_constructor('',YAMLTagIgnorer.check_tags)

class YAMLTagCat(yaml.SafeLoader):
    """
    Collect all tags in a YAML file.
    """
    def namecat(self,suffix,node):
        # note that you cannot subclass yaml.Loader to build YAMLTagCat and 
        #   then expect to use yaml.SafeLoader below because it still runs 
        #   any code in object/apply tags so be sure to subclass the loader
        #   that you want. in this case we just want the tag names so we have
        #   subclassed the SafeLoader, and yaml.Loader is therefore safe
        try: this = yaml.Loader.construct_mapping(self,node)
        # if the child is not a mapping we stop recursion
        except: this = {}
        has_tag = getattr(node,'tag',None)
        if has_tag: this['_tag_name'] = has_tag
        return this

# catalog of tags in a yaml file
YAMLTagCat.add_multi_constructor('',YAMLTagCat.namecat)

def YAMLTagFilter(*tags):
	"""
	Subclass the YAMLTagIgnorer to ensure only a certain tag exists.
	That tag is annotated on the resulting tree. Everything is loaded safe.
	"""
	class YAMLCheck(YAMLTagIgnorer):
		def allow_target_tag(self,node):
			this = self.construct_mapping(node)
			# annotate the tree so you can see the tags
			this['_has_tag'] = node.tag 
			return this
	for target_tag in tags:
		YAMLCheck.add_constructor(target_tag,YAMLCheck.allow_target_tag)
	# all other tags are ignored
	YAMLCheck.add_multi_constructor('',YAMLCheck.check_tags)
	return YAMLCheck

def select_yaml_tag_filter(tree,target_tag):
	"""
	Select a node with a single target tag after processing with YAMLTagFilter.
	""" 
	cat = list(catalog(tree))
	# identify root keys with the target tag
	tagged = dict([(route[0],val) for route,val in cat
		if route[-1]=='_has_tag' and len(route)==2])
	keys = [i for i,j in tagged.items() if j==target_tag]
	if len(keys)==0:
		raise Exception('cannot find target_tag: %s'%(target_tag))
	elif len(keys)>1: 
		raise Exception('multiple keys with tag "%s": %s'%(target_tag,str(keys)))
	else: 
		# remove annotation in case it is going somewhere strict
		this = tree[keys[0]]
		this.pop('_has_tag')
		return this

def flatten_recursive(this):
	"""Recursively flatten a list."""
	# via: https://stackoverflow.com/a/35415963
	out = []
	for item in this:
		if not isinstance(item,list):
			out.append(item)
		else:
			out.extend(flatten_recursive(item))
	return out

def yaml_tag_merge_list(self,node):
	"""
	Flatten a list in YAML. Note that this a much-requested and highly useful
	non-native YAML feature. 
	"""
	# this solution was too complex: https://stackoverflow.com/a/29620234
	this = [self.construct_sequence(i) for i in node.value]
	return flatten_recursive(this)

# generic !merge_lists tag is highly useful
yaml.add_constructor('!merge_lists',yaml_tag_merge_list)

def yaml_tag_strcat(self,node):
	"""
	Concatenate strings.
	Originally developed to concatenate spack specs and avoid redundancy.	
	"""
	return " ".join(self.construct_sequence(node))

yaml.add_constructor('!strcat',yaml_tag_strcat)

def yaml_tag_strcat_custom(joiner):
	"""Custom string concatenation in yaml."""
	def yaml_tag_strcat(self,node):
		return joiner.join(self.construct_sequence(node))
	return yaml_tag_strcat

#! difficulty outsourcing this to lib.spack
yaml.add_constructor('!chain',yaml_tag_strcat_custom(" ^"))

def yaml_tag_orthoconf(self,node):
	"""Tag to check the ortho.conf for a value."""
	from .config import conf
	if len(node.value)!=2: raise Exception('orthoconf tag requires two '
		'arguments: a key and a default')
	# we expect two arguments
	key,default = [i.value for i in node.value]
	return conf.get(key,default)

yaml.add_constructor('!orthoconf',yaml_tag_orthoconf)

def yaml_hook(tag):
	"""Make functions into YAML hooks."""
	# note that this can be used as a decorator for brevity
	if not tag.startswith('!'): 
		tag = '!%s'%tag
	def decorator(func):
		@functools.wraps(func)
		def yaml_to_function(self,node):
			return func(self,node)
		yaml.add_constructor(tag,yaml_to_function)
		return yaml_to_function
	return decorator

