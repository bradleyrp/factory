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

<a id="current"></a>
# Proof of concept

[2020.09.09] Completed minimal demo with a restricted Lmod tree. Included a tool for running concretize. Started testing from scratch. Considered complexity in the execution loop and decided on a minor refactor in the medium term. Until then, added features to point the code to an external spack source tree. Added the `!orthoconf` tag to accomplish this elegantly. New deployment instructions follow.

~~~
# clone to ~/work/stack
# reset everything
cd ~/work/stack
rm -rf ~/work/spack
rm -rf ./local
rm config.json
# install spack
make use specs/cli_spack.yaml
# setup spack
cd ~/work/
git clone https://github.com/spack/spack
mkdir spack/envs-spack
# set the paths
cd ~/work/stack
make set spack /home/rpb/work/spack
make set spack_envs /home/rpb/work/spack/envs-spack
make set spack_mirror_name rfcache
make set spack_mirror_path /home/rpb/work/spack/mirror
# deploy
cd ~/work/stack
make rf go do=setup 2>&1 | tee log
# onetime gpg
make rf gpg
# patch gromacs
patch ~/work/spack/var/spack/repos/builtin/packages/gromacs/package.py specs/rockfish/spack-gromacs-patch.txt	
# block home spack in development until we find out which command makes it
mkdir ~/.spack
chmod -rwx ~/.spack
# inside a screen, start the build
make rf go do=setup 2>&1 | tee log
# teardown test: remove the production demployment
rm -rf ~/local/stack
time (make rf go do=setup 2>&1 | tee log && make rf go do=gmxdemo 2>&1 | tee log)
~~~

The teardown above for Lmod, the GROMACS example, and supporting softwware, takes less than six minutes on a fast machine using the buildcache. Pending **issue**: the initial build procedure uses `~/.spack/cache` which means our `misc_cache` override is failing during build, but not after teardown and reinstallation from the buildcache.

# Rockfish buildout

[2020.09.10] Now that the code is working we can start adding compilers and packages in a systematic way. Our first objective is to build a single compiler, openmpi, and Python.

