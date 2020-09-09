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
