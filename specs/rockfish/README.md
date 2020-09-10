# Index

1. Current instructions for testing this proof-of-concept code is [below](#current).

# Rockfish Software Development Roadmap

## Bluecrab history

The `bluecrab.yaml` on the `bluecrab` branch was used to test and deploy spack on *Blue Crab* in a way that accomodated the stateless operating system. Circa September, 2020 we started building out `spack_tree.yaml` in a way that incorporates new Spack features. These notes will cover deployment to the next-generation cluster, codenamed *Rockfish*. 

## Objectives

We would like to incorporate the following features into the Rockfish software stack:

1. Robust software provided by [Spack](https://spack.io/).
2. Usability for academic researchers, particularly regarding package redundancy and simplicity.
3. Maintenance options for easy installation of new packages by any member of our team.
4. Integration and regression testing.
5. Optimal performance.

## Roadmap, ca 2020.09.07

For the forseeable future, we have the following development objectives.

1. Build a minimal, usable interface to the yaml specifications which deploy the code which is ideally simpler than the method we used on Blue Crab.
2. Use the build cache to share maintenance between workers and retire the original decoy-deployment method which was necessary to compile with Spack on Blue Crab.
3. Include a method for using external MPI and Intel compilers.
4. Design the module system to avoid hashes while still offering a complete index of underlying codes.
5. Include portal tools like RStudio and Jupyter.
6. Include an implementation of automatic Singularity containers via [Community Collections](https://github.com/community-collections).
7. Include regression and integration testing and frequent updates to the stack.

# 2020.09.08

Recent improvements in the factory provide more elegant use of YAML for configuration. Started `specs/rockfish.yaml` as the admin-facing interface which uses `specs/spack_rockfish.yaml` as the pure Spack instructions. Implemented oversight of mirrors in `lib.spack`. Added a feature which takes a single environment from the pure Spack instructions and modifies it for deployment outside of the site, for example to a production `install_tree`. Started adding a setup feature to compile Lmod. When this is working, we will proceed to build examples to ensure minimal redundancy for the users. Incoming features include:

- Implement upstream dependency parsing for build cache.
- Location for a Rockfish-specific spack source tree.
- Migration to the test cluster for testing.
- Retirement of decoy features from Blue Crab to a secondary location.
- Automate the signatures or at least a hook to them.
- Proof of concept for minimizing redundancy in the user modules.

Completed the upstream dependency feature and deployed Lmod and an example code (Gromacs) to a remote `install_tree` as a proof of concept. Now we can resume work to develop spack environments that produce minimally-redundant packages for the user space.

Minimal example:

~~~
make spack specs/rockfish.yaml setup
make spack specs/rockfish.yaml deploy do=gromacs_centos8_gpu
source ~/local/stack/linux-centos8-zen/gcc-8.3.1/lmod-8.3-6oolrjmxq5n4fjjd7zek3tnfb2ftv4l3/lmod/lmod/init/bash
module use $HOME/local/stack/lmod/linux-centos8-x86_64/Core
module avail
ml openmpi
ml gromacs
~~~

# Proof of concept

[2020.09.09] Completed minimal demo with a restricted Lmod tree. Included a tool for running concretize. Started testing from scratch. Considered complexity in the execution loop and decided on a minor refactor in the medium term. Until then, added features to point the code to an external spack source tree. Added the `!orthoconf` tag to accomplish this elegantly. New deployment instructions follow in the next section

The teardown above for Lmod, the GROMACS example, and supporting softwware, takes less than six minutes on a fast machine using the buildcache. Pending **issue**: the initial build procedure uses `~/.spack/cache` which means our `misc_cache` override is failing during build, but not after teardown and reinstallation from the buildcache.

<a id="current"></a>
## Instructions to deploy

### Create a centralized spack source tree

**Onetime only.** Note that we may need to modify the spack source and quickly build new software before we can submit a pull request. On Blue Crab we also made custom modifications related to stateless operation. In order to maintain a cluster-specific spack branch, we clone a central copy.

~~~
# choose an appropriate paths
export SPACK_CENTRAL=$HOME/work/spack
git clone https://github.com/spack/spack $SPACK_CENTRAL
# create branches as necessary
~~~

### Setup prefix, environments, and mirror

**Onetime only.** Make folders for the production or testing target (`$SPACK_PREFIX`) as well as a place for the buildcache and environments.

~~~
export SPACK_PREFIX=$HOME/local/stack
export SPACK_MIRROR_NAME=rfcache
export SPACK_MIRROR_PATH=$HOME/work/mirror-$SPACK_MIRROR_NAME
export SPACK_ENVS=$HOME/work/spackenvs
mkdir $SPACK_PREFIX
mkdir $SPACK_ENVS
~~~

### Clone the Rockfish factory code

**Onetime only.** Clone this code for personal use. Each contributor (or maintainer or admin) can do this. In the example above I have used the home directory, but when we deploy this on the cluster we can choose shared locations.

~~~
export SPACK_FACTORY=$HOME/work/stack
git clone https://github.com/bradleyrp/factory -b bluecrab $SPACK_FACTORY
cd $SPACK_FACTORY
~~~

### Configure

**Onetime only.** Connect the factory to shared locations.

~~~
cd $SPACK_FACTORY
make set spack $SPACK_CENTRAL
make set spack_envs $SPACK_ENVS
make set spack_mirror_name $SPACK_MIRROR_NAME
make set spack_mirror_path $SPACK_MIRROR_PATH
make set spack_prefix $SPACK_PREFIX
# check your work
make config
# install the spack extensions to the factory
make use specs/cli_spack.yaml
~~~

### GPG keys

**Onetime only.** Make some GPG keys.

~~~
cd $SPACK_FACTORY
source env.sh spack
spack gpg init
spack gpg create "John Doe" "jdoe123@gmail.com"
~~~

### Build

Now we are ready to build Lmod and the demonstration codes.

~~~
# build in a screen so we can go get coffee or our connection can be interrupted
screen -S spack
cd $SPACK_FACTORY
# make a log because screen prevents scrolling up to see elaborate errors
time make rf go do=setup 2>&1 | tee log
# make the demo
time make rf go do=gmxdemo 2>&1 | tee -a log
~~~

# Rockfish buildout

[2020.09.10] Now that the code is working we can start adding compilers and packages in a systematic way. Our first objective is to build a single compiler, openmpi, and Python. The following example has been customized for testing in Centos8, where the default compiler is GCC 8.3.1.

~~~
cd $SPACK_FACTORY
time make rf go do=gcc-8-compiler 2>&1 | tee -a log
~~~
