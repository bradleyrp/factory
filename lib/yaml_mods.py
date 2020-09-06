#!/usr/bin/env python

import yaml

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

class YAMLTagIgnorer(yaml.SafeLoader):
    """
    Detect yaml recipes with Tags. Works with the constructor below.
    """
    def check_tags(self,suffix,node):
        # return a placeholder that notes tags later checked recursively
        # this halts after seeing the first tag so you cannot use it to
        #   catalog all tags in a tree
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
