#!/usr/bin/env python

"""
Use with `./fac` or `make`.
The first time you import the ortho module it will bootstrap a makefile.
The Interface(Parser) command holds the CLI functions. 
Note that this CLI interface uses the script-connect makefile (not the 
ortho-connect makefile) and the Parser. This is the preferred CLI method.
"""

# the envs function below skips our overloaded print_function somehow
from __future__ import print_function
import os,sys,re,shutil,json,glob

import ortho
from ortho import bash
from ortho import Parser,StateDict
from ortho import requires_python,requires_python_check
from ortho import conf,treeview
from ortho import Handler
from ortho import tracebacker
from ortho.installers import install_miniconda
from ortho.statetools import StateDict,Cacher,Convey
from ortho.replicator.replicator_dev import ReplicateCore
from json import JSONEncoder

class FactoryConfig(StateDict):
    """
    Manage the factory configuration as a cache.
    """
    def __init__(self):
        self._debug = False
        self['envs'] = {}
        self['spots'] = {}
    def add_env(self,spot,kind,file=None,**kwargs):
        """Register an evironment spot."""
        self['envs'][spot] = dict(kind=kind,file=file,**kwargs)

# state holds config
state = FactoryConfig()

def get_uname():
    """
    Check the platform and architecture of the system. Useful for docker.
    """
    this = os.uname()
    if sys.version_info<(3,0):
        this = dict([(k,this[kk]) for kk,k in 
            [(0,'sysname'),(1,'nodename'),(2,'release'),(4,'machine')]])
        return this
    else: return dict(sysname=this.sysname,release=this.release,
        machine=this.machine,nodename=this.nodename)

def set_env_cursor(spot):
    """
    Update a cursor which specifies an environment we should always use.
    """
    if os.path.islink('.envcursor'): 
        os.unlink('.envcursor')
    os.symlink(spot,'.envcursor')

class Action(Handler):
    """Generic state-based code."""
    #! removed this requirement: requires_python('ipdb')
    def basic(self,lib,path,function,spec={}):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.mkdir(path)
        this = ortho.importer(lib)
        spec['spot'] = path
        this[function](**spec) 
    def python(self,script):
        """Run a python script from a yaml file."""
        #! unprotected execution
        exec(script)
    def bash(self,bash):
        """Run a bash script from a yaml file."""
        ReplicateCore(script=bash)

class MakeUse(Handler):
    def update_config(self,config):
        """Alter the local config."""
        # unroll the config so we merge without overwrites
        #   otherwise repeated `make use` would override not accumulate changes
        # previously used ortho.conf directly but now we use self.cache
        #! does this mean it is deprecated
        #! the following was moved to ortho.delve_merge
        this_conf = self.state
        unrolled = ortho.catalog(config)
        for route,val in unrolled:
            ortho.delveset(this_conf,*route,value=val)
        ortho.write_config(this_conf)

def cache_closer(self):
    """Hook before writing the cache."""
    # is this the correct way to pass a hook function into a class method?
    # remove the settings from the cache before saving
    #   since they should be written back to the settings if they are important
    for key in ['settings','settings_raw']:
        if key in self.cache:
            del self.cache[key]

@Cacher(
    cache_fn='config.json',
    closer=cache_closer,
    cache=state,)
class Interface(Parser):
    """
    A single call to this interface.
    """
    # cli extensions add functions to the interface automatically
    subcommander = ortho.conf.get('cli_extensions',{})
    name = "Factory Interface".upper()
    """
    Note that this interface works with fac to accept pipes and pick python:
        echo "import sys;print(sys.version_info);sys.exit(0)" | \
            python=python2 make debug
    """

    def _try_except(self,exception): 
        # include this function to throw legitimate errors
        tracebacker(exception)
        #! previously: `raise exception` but this caused repeats

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
        #? consider adding this to `make do` via yaml tag
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

    def do(self,what,debug=False):
        """
        Create something from a spec.
        This is the PRIMARY INTERFACE to most features.
        """
        #! we cannot use the requires_python decorator with Parser
        requires_python_check('yaml')
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
                print('status found a spec with YAML tags at %s'%what)
                spec = yaml.load(text,Loader=yaml.Loader)
                if debug: 
                    #! cleaner option is needed here
                    #! only works with ./fac --debug
                    import ipdb;ipdb.set_trace()
                    #! fix this. rescue self.debug()
                print('status finished with YAML spec')
            # standard execution
            else: 
                spec = yaml.load(text,Loader=yaml.Loader)
                #! previously tried to add **kwargs from do to spec['kwargs']
                Action(**spec).solve
        else: raise Exception('unclear what: %s'%what)

    def build_docs(self,source='',build=''):
        """Build the documentation. 
        Usage: `make build_docs source=docs/source build=docs/build`"""
        kwargs = {}
        if source: kwargs['source'] = source
        if build: kwargs['build'] = build
        ortho.documentation.build_docs(**kwargs)

    def nuke(self,sure=False):
        """Reset everything. Useful for testing."""
        from ortho import confirm
        dns = ['apps','spack','conda','local','config.json','cache.json']
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
        # we must clear the cache or else it waits in memory and is written
        #   out again with the same contents as before the nuke. this is 
        #   actually a healthy feature for the cache but defies the nuke idea
        self.cache = {}

    def envs(self,name=None):
        """List environments. Used by `env.sh` to source them."""
        # special keyword to source spack
        if name=="_spack":
            if 'spack' not in ortho.conf: 
                raise Exception("spack is not registered")
            print("source %s"%os.path.join(ortho.conf['spack'],'share','spack','setup-env.sh'))
            return
        toc = {}
        for env,detail in self.cache.get('envs',{}).items():
            shortname = os.path.basename(env)
            if shortname in toc: raise Exception('collision: %s'%shortname)
            toc[shortname] = dict(kind=detail['kind'],spot=env)
        if not name:
			# casting strings below to avoid prefix for unicode in python 2
            print('status available environments: %s'%str(list(str(i) for i in toc.keys())))
            return
        else:
            if name not in toc: 
                raise Exception('cannot find %s'%name)
        if toc[name]['kind']=='venv':
            print('source %s/bin/activate'%toc[name]['spot'])
        elif toc[name]['kind']=='conda':
            print('source %s/bin/activate %s'%(
                os.path.relpath(os.path.join(toc[name]['spot'],'..','..')),
                os.path.join(toc[name]['spot'])))
        else: 
            raise Exception('unclear kind: %s'%toc[name]['kind'])

    def sim(self,path):
        """Create a simulation from a remote automacs."""
        #! remote automacs location is hardcoded now
        bash('make -C ../automacs tether %s'%os.path.abspath(path))

    def repl(self,name,rebuild=False):
        """Connect to ortho.replicator."""
        #! this will be superceded by `make docker` from lib.replicator
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
            Convey(state=self.cache)(MakeUse)(**changes).solve
        else: raise Exception('unclear what: %s'%what)

    def script(self,file,name,spot=None):
        """
        Run a script with the file/name pattern.
        """
        from lib.generic import FileNameSubSelector
        from lib.generic import RunScript
        # compose the RunScript in the FileNameSubSelector pattern
        class This(FileNameSubSelector): Target = RunScript
        This(file=file,name=name,spot=spot)

    def venv(self,cmd,file=None,spot='local/venv'):
        """
        Manage a virtual environment.
        """
        # usage: python=python2 make venv create 
        if file and not os.path.isfile(file):
            raise Exception('cannot find %s'%file)
        #! spot should be hookable
        #! use subparsers?
        if cmd=='create':
            # +++ assume if it exists it was installed correctly
            if os.path.isdir(spot):
                raise Exception('already exists: %s'%spot)
            bash('python -m venv %s'%spot)
            if not file:
                # default venv packages
                packages = ['pyyaml']
                for pack in packages:
                    bash('source %s/bin/activate && pip install %s'%(
                        spot,pack))
            else: bash('source %s/bin/activate && '
                'pip install -r %s'%(spot,file))
            #!! set_env_cursor(os.path.join(spot))
        else: raise Exception('unclear command: %s'%cmd)
        # register this environment
        self.cache.add_env(spot=spot,kind='venv',file=file,uname=get_uname())

    def conda(self,file,spot='local/conda',use=True):
        """
        Build a conda environment.
        """
        if not os.path.isfile(file):
            raise Exception('cannot find %s'%file)
        print('status checking for miniconda')
        spot_rel = spot
        # +++ assume if spot exists and is directory then conda is installed
        spot = ortho.path_resolver(spot)
        # install if missing
        if not os.path.isdir(spot):
            install_miniconda(spot)
        # always update to install a sub-environment
        print('status updating environment from %s'%file)
        bash('%s env update --file %s'%(
            os.path.join(spot,'bin/conda'),file),announce=True)
        # get the prefix for the file to update the cursor
        with open(file) as fp: reqs = fp.read()
        # get the name with a regex
        name = re.findall(r'name:\s+(.*?)(?:\s|\n|\Z)',reqs)
        if name=='spack':
            print('warning this name collides with "spack" and cannot be '
                'sourced with the env.sh script')
        if len(name)!=1: raise Exception('cannot identify a name in %s'%file)
        else: name = name[0]
        # +++ assume name is the install location in conda/envs
        env_spot = os.path.join(spot,'envs',name)
        env_spot_rel = os.path.join(spot_rel,'envs',name)
        #!! disabled for now if use: set_env_cursor(env_spot)
        # register this environment
        print('status activate this environment with: '
            './fac activate %s'%env_spot_rel)
        self.cache.add_env(spot=env_spot_rel,kind='conda',
            file=file,uname=get_uname())

    def activate(self,spot):
        """
        Activate an environment.
        """
        envs = self.cache['envs']
        if spot not in envs:
            raise Exception('available envs: %s'%str(list(envs.keys())))
        env = envs[spot]
        uname = get_uname()
        for key in ['sysname','release','machine','nodename']:     
            if env['uname'][key]!=uname[key]:
                #! test this later
                raise Exception('refusing to activate because of a mismatch. '
                    'the environment has %s=%s but uname indicates %s=%s'%
                    (key,env['uname'][key],key,uname[key]))
        set_env_cursor(spot)

    def config(self):
        """Print the config."""
        print('status running python from %s'%sys.executable)
        import pprint
        pprint.pprint(self.cache)

    def check_config(self):
        """Check the config against an incoming pipe."""
        print('status waiting for a pipe')
        incoming = sys.stdin.read()
        match = False
        try: 
            expected = eval(incoming)
            match = expected==self.cache
        except Exception as e: 
            ortho.tracebacker(e)
        if not match:
            print('status expected config: %s'%str(incoming))
            print('status current config: %s'%str(self.cache))
        print('status result: %s'%('PASS' if match else 'FAIL'))
        if not match: raise Exception('mismatched config')

    def bootstrap(self,name=None,suffix=None):
        """Bootstrap a configuration."""
        """ CURRENT Tests
        make bootstrap name=venv suffix=macos
        make bootstrap name=conda suffix=macos #! conda is immovable
        """
        sources = glob.glob('lib/tests/test_bootstrap_*.sh')
        regex = 'lib/tests/test_bootstrap_(.+).sh'
        sources = [re.match(regex,i).group(1) for i in sources]
        if not name:
            print('usage make bootstrap name=<name> (suffix=<suffix>)')
            print('usage the suffix is appended to the environment path')
            print('status available bootstrap names: %s'%str(sources))
            return
        # note that this simply calls some bash scripts that serve as tests
        print('status bootstrap %s%s'%(
            name,' with suffix %s'%suffix if suffix else ''))
        cmd = 'bash lib/tests/test_bootstrap_%s.sh'%name
        if suffix: cmd += ' %s'%suffix
        #! add protection agaist `./fac nuke --sure`
        ortho.bash(cmd,scroll=True,announce=True)

if __name__ == '__main__':
    # the ./fac script calls this interface
    Interface()
