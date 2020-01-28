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

def yaml_tag_merge_list(self,node):
    """
    Flatten a list in YAML. Note that this a much-requested and highly useful
    non-native YAML feature. 
    #! consider moving to a more central location
    """
    data = []
    # adapted from: https://stackoverflow.com/a/29620234
    yield data
    for item in self.construct_sequence(node):
        data.extend(item)

# generic !merge_lists tag is highly useful
yaml.add_constructor('!merge_lists',yaml_tag_merge_list)
