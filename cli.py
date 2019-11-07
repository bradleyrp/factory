#!/usr/bin/env python

"""
Use with `./fac` or `make`.
The first time you import the ortho module it will bootstrap a makefile.
The Interface(Parser) command holds the CLI functions. 
Note that this CLI interface uses the script-connect makefile (not the 
ortho-connect makefile) and the Parser. This is the preferred CLI method.
"""

import os,re,shutil,json

import ortho
from ortho import bash
from ortho import Parser,StateDict
from ortho import requires_python,requires_python_check
from ortho import conf,treeview
from ortho import Handler
from ortho import tracebacker
from ortho.installers import install_miniconda


# manage the state
#! how does this work? test it.
global_debug = True
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
        bash('conda/bin/conda env update --file %s'%file,announce=True)
        # get the prefix for the file to update the cursor
        with open(file) as fp: reqs = fp.read()
        # get the name with a regex
        name = re.findall(r'name:\s+(.*?)(?:\s|\n|\Z)',reqs)
        if len(name)!=1: raise Exception('cannot identify a name in %s'%file)
        else: name = name[0]
        # +++ assume name is the install location in conda/envs
        env_spot = os.path.join(os.getcwd(),'conda','envs',name)
        update_factory_env_cursor(env_spot)

class Action(Handler):
    """Generic state-based code."""
    requires_python('ipdb')
    def basic(self,lib,path,function,spec={}):
        #! note that the replicator has a method for this
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.mkdir(path)
        this = ortho.importer(lib)
        spec['spot'] = path
        this[function](**spec) 
    def script(self,script):
        #! highly dangerous. unprotected execution!
        #!   consider using the replicator instead?
        exec(script)
    def command(self,command,**kwargs):
        import ipdb;ipdb.set_trace()

class User(Handler):
    def update_config(self,config):
        """Alter the local config."""
        ortho.conf.update(**config)
        ortho.write_config(ortho.conf)

class Interface(Parser):
    """
    A single call to this interface.
    """
    # cli extensions add functions to the interface automatically
    subcommander = ortho.conf.get('cli_extensions',{})

    def _try_except(self,exception): 
        # include this function to throw legitimate errors
        tracebacker(exception)
        raise exception

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
        Dev note: only single-word arguments can pass through.
        Use the `help` argument to see the available targets.
        """
        if arg=='help': arg = ''
        ortho.bash('make --file ortho/makefile.bak'+(' '+arg if arg else ''))

    def do(self,what,debug=False,**kwargs):
        """
        Create something from a spec.
        This is the PRIMARY INTERFACE to most features.
        """
        #! we cannot use the requires_python decorator with Parser
        requires_python_check('ipdb','yaml')
        #!!! requires the EcoSystem. import it here
        import yaml
        if os.path.isfile(what):
            with open(what) as fp: text = fp.read()
            from lib.yaml_mods import YAMLTagIgnorer
            # the YAMLTagIgnorer decorates a placeholder tree with _has_tag
            spec = yaml.load(text,Loader=YAMLTagIgnorer)
            # detect any tags
            tagged = any(route[-1]=='_has_tag' and val==True 
                for route,val in ortho.catalog(spec)) 
            # note that we could add some kind of protection here
            if tagged:
                print('status found a spec with YAML tags')
                spec = yaml.load(text,Loader=yaml.Loader)
                if debug: 
                    #! cleaner option is needed here
                    import ipdb;ipdb.set_trace()
                    #! fix this. rescue self.debug()
                print('status finished with YAML spec')
            # standard execution
            else: 
                import ipdb;ipdb.set_trace()
                spec = yaml.load(text,Loader=yaml.Loader)
                if kwargs and 'kwargs' in spec:
                    raise Exception('collision')
                    spec['kwargs'] = kwargs['kwargs']
                Action(**spec).solve
        else: raise Exception('unclear what: %s'%what)

    def build_docs(self,source='',build=''):
        kwargs = {}
        if source: kwargs['source'] = source
        if build: kwargs['build'] = build
        ortho.documentation.build_docs(**kwargs)

    def nuke(self,sure=False):
        """Reset everything. Useful for testing."""
        from ortho import confirm
        dns = ['apps','spack','conda']
        links = ['.envcursor']
        if sure or confirm('okay to nuke everything?'):
            for dn in dns:
                if os.path.isdir(dn): 
                    print('removing tree: %s'%dn)
                    shutil.rmtree(dn)
            for link in links:
                if os.path.islink(link):
                    print('unsetting %s'%link)
                    os.unlink(link)

    def envs(self):
        """
        Useful help for activating environments. Called by env.sh.
        """
        try_this = 'try ./fac conda <requirements>'
        if not os.path.isfile('conda/bin/activate'):
            raise Exception('conda is not installed. '+try_this)
        toc = bash('conda/bin/conda-env list --json',scroll=False)
        them = json.loads(toc['stdout']).get('envs',[])
        base_dn = os.path.join(os.getcwd(),'conda','envs')
        them = [os.path.relpath(i,base_dn) for i in them]
        if not them:
            raise Exception('cannot find environments. '+try_this)
        print('status available environments:')
        for t in them: 
            if t.startswith('..'): continue
            print('status  %s'%t)
        print('status activate an environment with: '
            'source env.sh <name>')
        print('status or use: source conda/bin/activate conda/envs/<name>')
        print('status deactivate with: conda deactivate')

    def sim(self,path):
        """Create a simulation from a remote automacs."""
        #! remote automacs location is hardcoded now
        bash('make -C ../automacs tether %s'%os.path.abspath(path))

    def repl(self,name,rebuild=False):
        """Connect to ortho.replicator."""
        print('status calling ortho.replicator')
        args = [name]
        if rebuild: args += ['rebuild']
        ortho.replicator.repl(*args)

    def use(self,what):
        """Update the config with a prepared set of changes."""
        requires_python_check('yaml')
        import yaml
        if os.path.isfile(what):
            with open(what) as fp: text = fp.read()
            changes = yaml.load(text,Loader=yaml.SafeLoader)
            User(**changes).solve
        else: raise Exception('unclear what: %s'%what)

if __name__ == '__main__':
    # the ./fac script calls cli.py to make the interface
    Interface()
