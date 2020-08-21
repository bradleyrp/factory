# run from factory root with: make -C specs/slurm-docker <command>
.PHONY: stop clean deepclean make_volumes build
all:
stop:
	for i in slurmctld accounts c1 slurmdbd mysql; do \
		docker stop $${i}; \
		docker kill $${i}; \
		docker rm $${i}; \
	done
clean:
	docker system prune
	docker volume rm \
	etc_munge etc_slurm slurm_jobdir var_lib_mysql var_log_slurm
deepclean:
	docker rmi -f marcc-hpc:testcluster
	docker rmi -f marcc-hpc:ldap
make_volumes:
	for name in etc_munge etc_slurm var_log_slurm var_lib_mysql slurm_jobdir \
	ldap_data ldap_config; do \
		docker volume create --name=$${name}; \
	done
build:
	make -C ../../ docker specs/slurm-docker/marcc-hpc.yaml testcluster_build rebuild
	make -C ../../ docker specs/slurm-docker/marcc-hpc.yaml testcluster_ldap_build rebuild
