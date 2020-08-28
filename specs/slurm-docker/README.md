The following documentation is hosted on the [factory github](https://github.com/bradleyrp/factory/tree/bluecrab/specs/slurm-docker) however the portal code will point elsewhere (possibly a private repository [here](https://github.com/marcc-hpc/portal)).

# Setup Instructions

1. Build docker volumes and containers with the [latest instructions](#setup-latest).
2. Deploy an application [like coldfront](#coldfront-quickstart).

# Historical Notes

## Historical notes [2020.06.06]

Deprecated notes from the initial setup. 

~~~
# ca 2020.06.06 deploying the cluster (notes cleaned from factory.md)
# stop everything if you are in development
for i in slurmctld accounts c1 slurmdbd mysql; do docker stop $i; docker kill $i; docker rm $i; done
docker volume ls
docker system prune
docker volume rm etc_munge etc_slurm slurm_jobdir var_lib_mysql var_log_slurm
docker volume ls
# if you need to recreate the images, remove them first
# docker rmi marcc-hpc:accounts
# docker rmi slurm-docker-cluster:19.05.1
# create the volumes
for name in etc_munge etc_slurm var_log_slurm var_lib_mysql slurm_jobdir; do docker volume create --name=$name; done
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_build
# check the volume
docker run -it --rm -v $PWD:/src -v etc_slurm:/tmp ubuntu:bionic ls /tmp # nothing there yet
# see recap above (we had a slurm.conf in a persistent volume and errors there were causing it to crash)
# in the following sequence we are debugging our slurm.conf
# now restart the cluster
make docker specs/slurm-docker/marcc-hpc.yaml testcluster
# eventually the controller dies again but this is okay
# now we can actually check the controller to see what the error is
cd up-testcluster
docker-compose run slurmctld bash
gosu munge /usr/sbin/munged
gosu slurm /usr/sbin/slurmctld -Dvvv
# switch to a different configuration
# try a basic conf
docker run --rm -v $PWD/specs/slurm-docker/:/src -v etc_slurm:/tmp ubuntu:bionic cp -av /src/slurm.basic.conf /tmp/slurm.conf
make docker specs/slurm-docker/marcc-hpc.yaml testcluster
cd up-testcluster
# the cluster is running now
docker-compose run slurmctld bash
~~~

<a id="setup-latest"></a>
## Setup notes, retest [2020.08.21] 

~~~
git clone https://github.com/bradleyrp/factory -b bluecrab
cd factory
./fac use specs/cli_replicator.yaml
make -C specs/slurm-docker stop
make -C specs/slurm-docker clean # this erases volumes so be careful
make -C specs/slurm-docker deepclean # this erases images so be careful
make -C specs/slurm-docker make_volumes
make -C specs/slurm-docker build
# run the command
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_build rebuild
make docker specs/slurm-docker/marcc-hpc.yaml testcluster
# visit the container for development
docker exec -it accounts bash
# develop in the container
cd /opt/
# proposed github location
git clone https://github.com/marcc-hpc/portal
# ongoing development activity can happen at this repository
# later run an ldap server
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_ldap
# inspect dockerfiles for export to native docker
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_ldap tour
~~~

<a id="coldfront-quickstart"></a>
## Minimal Coldfront setup [2020.08.27]

~~~
# via https://github.com/ubccr/coldfront
# builting this in /opt which is a persistent volume
# via docker exec -it accounts bash 
cd /opt
mkdir coldfront_app
cd coldfront_app
git clone https://github.com/ubccr/coldfront.git
python3.6 -mvenv venv
source venv/bin/activate
cd coldfront
pip install wheel
pip install -r requirements.txt
# copy settings
cp coldfront/config/local_settings.py.sample coldfront/config/local_settings.py
cp coldfront/config/local_strings.py.sample coldfront/config/local_strings.py
# setup
python manage.py initial_setup
python manage.py load_test_data
python manage.py runserver 0.0.0.0:8000
~~~
