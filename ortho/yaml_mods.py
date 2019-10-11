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
        return {'_has_tag':True}

# the YAMLTagIgnorer is constructed on any tag.
YAMLTagIgnorer.add_multi_constructor('',YAMLTagIgnorer.check_tags)
