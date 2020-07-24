#!/usr/bin/env python

import os,sys
from .bash import shell_script,command_check

if sys.platform=='darwin':
	miniconda_source = 'Miniconda3-latest-MacOSX-x86_64.sh'
else: miniconda_source = 'Miniconda3-latest-Linux-x86_64.sh'

# generic build script in temporary space
script_temp_build_base = """
set -e
set -x
# environment here
%(source_env)s
set pipefail
tmpdir=$(mktemp -d)
here=$(pwd)
cd $tmpdir
echo "[STATUS] temporary build directory is $tmpdir"
# build here
%%(script)s
cd $here
rm -rf $tmpdir
"""

# source environment
script_source_env = """
source %(miniconda_activate)s
conda activate %(envname)s
"""

# option to build with an environment
script_temp_build = script_temp_build_base % dict(source_env='')

# installation method for miniconda
install_miniconda_script = script_temp_build % dict(script="""
wget --progress=bar:force """
"""https://repo.anaconda.com/miniconda/%(miniconda_source)s
bash %(miniconda_source)s -b -p %%(miniconda_path)s -u
"""%dict(miniconda_source=miniconda_source))

def install_miniconda(spot):
    """
    Install miniconda from a temporary directory using a script.
    """
    #! it would be nice to use a command check for wget here
    script = (install_miniconda_script % {'miniconda_path':spot})
    # use of the logfile ensures this is safe for Python 2
    fn_log = 'log-install-miniconda'
    result = shell_script(script,log=fn_log)
    if result==True and os.path.isfile('log-install-miniconda'): 
    	os.remove(fn_log)
