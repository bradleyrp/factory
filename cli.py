#!/usr/bin/env python

#! yo make conda is busted! it uses the folder of the same name!

"""
Use with `./fac` or `make`.
The first time you import the ortho module it will bootstrap a makefile.
The Interface(Parser) command holds the CLI functions. 
Note that this CLI interface uses the script-connect makefile (not the 
ortho-connect makefile) and the Parser. This is the preferred CLI method.
"""

import os,re

import ortho
from ortho import bash
from ortho import Cacher,Parser,StateDict,requires_python
from ortho import conf,treeview
from ortho import Handler
from ortho.installers import install_miniconda

# manage the state
#! how does this work? test it.
global_debug = False
state = StateDict(debug=global_debug)

def update_factory_env_cursor(spot):
    """
    Update a cursor which specifies an environment we should always use.
    """
    if os.path.islink('.envcursor'): 
        os.unlink('.envcursor')
    os.symlink(spot,'.envcursor')

def cache_closer(self):
    """Hook before writing the cache."""
    pass

class Conda(Handler):
    """
    Manage conda environment installation
    """
    def _install_check(self):
        """
        Install miniconda if absent. No automatic removal on failure.
        """
        #! dev: automatically register this preliminary function with Handler?
        spot = os.path.realpath(ortho.conf.get('miniconda_root','./conda'))
        # +++ assume if spot exists and is directory then conda is installed
        if not os.path.isdir(spot):
            return install_miniconda(spot)
    def make(self,file=None):
        """
        Make a conda environment.
        """
        if not os.path.isfile(file):
            raise Exception('cannot find %s'%file)
        print('status checking for miniconda')
        self._install_check()
        print('status updating environment from %s'%file)
        bash('conda/bin/conda env update --file %s'%file)
        # get the prefix for the file to update the cursor
        with open(file) as fp: reqs = fp.read()
        # get the name with a regex
        name = re.match(r'name:\s+([^\s\n]+)',reqs).group(1)
        # +++ assume name is the install location in conda/envs
        env_spot = os.path.join(os.getcwd(),'conda','envs',name)
        update_factory_env_cursor(env_spot)
        
@Cacher(
    cache_fn='cache.json',
    closer=cache_closer,
    cache=state,)

class Interface(Parser):
    """
    A single call to this interface.
    """

    def _get_settings(self):
        import yaml
        with open(cc_user) as fp:
            raw = yaml.load(fp, Loader=yaml.SafeLoader)
        # save the rw yaml
        self.cache['settings_raw'] = raw
        # resolve the yaml with defaults if they are missing
        settings = settings_resolver(raw)
        self.cache['settings'] = settings
        return settings

    def conda(self,file):
        """Update or install a conda environment."""
        Conda(file=file).solve

    def update_conda(self):
        """
        Update the conda version that supports the environments.
        """
        bash('conda/bin/conda update -y -n base -c defaults conda')
        
    def ortho(self,arg):
        """
        Recover the ortho targets.
        We use the script-connect makefile but some ortho functions are
        available with the ortho-connect makefile.
        Only single-word arguments can pass through
        We cannot name this function "ortho" or make will ignore it.
        Dev note: rename this ortho and fix the above problem.
        Send "help" to get the equivalent of `make ortho` which returns targets.
        """
        if arg=='help': arg = ''
        ortho.bash('make --file ortho/makefile.bak'+(' '+arg if arg else ''))

if __name__ == '__main__':
    # the ./fac script calls cli.py to make the interface
    Interface()
