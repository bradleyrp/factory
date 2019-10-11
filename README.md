## The streamline branch

This branch is a refactor in an orphan branch alongside the current `bradleyrp/factory` fork of `biophyscode/factory`.

## Development with `ortho`

In order to develop this code you must retrieve a subtree from `ortho`.

~~~
# initial setup
git remote add ortho-up http://github.com/bradleyrp/ortho
git subtree add --prefix=ortho ortho-up master
# later push and pull with
git subtree --prefix=ortho pull ortho-up master --squash
git subtree --prefix=ortho push ortho-up master
~~~

## Installation instructions

This branch is cloned via `git clone https://github.com/bradleyrp/factory -b streamline`. Find a central location to install it.

~~~
git clone http://github.com/bradleyrp/factory -b streamline
cd factory
make conda specs/env_std_md_extra.yaml  
make do specs/install_gromacs_native.yaml 
# wait until screen-install-gromacs.log disappears
# if you have a modeller license
make do specs/config_modeller_license.yaml
# load the environment every time
source ./local/env_gromacs_std.sh
# install automacs once
make do specs/install_automacs.yaml
# fetch automacs experiments
make -C automacs setup all
mkdir -p data
# choose a name for the simulation
make -C $AMXROOT tether $PWD/data/v002
cd data/v002
make clean sure && make remote protein
~~~
