# Historical notes

Deprecated notes. Under construction; see below.

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

Refactoring notes below:

~~~
git clone https://github.com/bradleyrp/factory -b bluecrab
cd factory
./fac use specs/cli_replicator.yaml
make -C specs/slurm-docker stop
make -C specs/slurm-docker clean # this erases volumes so be careful
make -C specs/slurm-docker deepclean # this erases images so be careful
make -C specs/slurm-docker make_volumes
make -C specs/slurm-docker build
~~~