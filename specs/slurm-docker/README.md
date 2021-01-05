The following documentation is hosted on the [factory github](https://github.com/bradleyrp/factory/tree/bluecrab/specs/slurm-docker). The notes below will explain how to use the factory code for testing SLURM and LDAP and Coldfront inside of a docker cluster. Preliminary development of a user portal occurs in a fork of Coldfront located in a private repository for MARCC at [`https://github.com/marcc-hpc/portal`](https://github.com/marcc-hpc/portal).

To set up a development environment for the portal, follow [the latest instructions below](#setup-latest).

# Historical Notes

## Historical notes [2020.06.06]

Deprecated notes from the initial setup. 

~~~
# ca 2020.06.06 deploying the cluster (notes cleaned from factory.md)
# stop everything if you are in development (added new names here as we added containers)
for i in slurmctld accounts c1 slurmdbd mysql adminer ldap ldap_admin postgres; do docker stop $i; docker kill $i; docker rm $i; done
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

## Setup notes [2020.08.21] 

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
for i in ldap ldap_admin; do docker stop $i; docker rm $i; done
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
python3.8 -m venv venv
source venv/bin/activate
cd coldfront
pip install wheel
pip install -r requirements.txt
# copy settings
cp coldfront/config/local_settings.py.sample coldfront/config/local_settings.py
cp coldfront/config/local_strings.py.sample coldfront/config/local_strings.py
# check sqlite version is high enough
python3.8 -c "import sqlite3; print(sqlite3.sqlite_version)"
# setup
python manage.py initial_setup
python manage.py load_test_data
python manage.py runserver 0.0.0.0:5000
# install more things
source /opt/coldfront_app/venv/bin/activate
cd /opt/coldfront_app/coldfront/
pip install -r requirements.txt
# upon revisit
source /opt/coldfront_app/venv/bin/activate
cd /opt/coldfront_app/coldfront/
python manage.py runserver 0.0.0.0:5000
~~~

<a id="coldfront"></a>
## Forking coldfront privately [2020.09.04]

In the current "setup notes", we cloned coldfront. To start developing locally, we should fork it into a private repository. Here is a summary of the method we used.

~~~
# new private repo at https://github.com/marcc-hpc/portal
# in the accounts container
cd /opt
# make a dev branch
git clone https://github.com/marcc-hpc/portal.git portal
cd portal-tmp
git checkout -b dev
git config --global user.email "bradleyrp@gmail.com" && git config --global user.name "Ryan Bradley" && git config --global push.default matching
git commit --allow-empty -m 'initial commit'
# push this up
git push origin dev
# now we are ready to get the fork
# note that when figuring this out, I kept portal dev with the empty commit in a separate folder in case I needed to do a git push --mirror https://github.com/marcc-hpc/portal.git
# strategy is to fetch the remote and push it back up
git remote add fork https://github.com/ubccr/coldfront
git fetch fork master
git checkout dev
git fetch origin dev
# now we merge theirs into ours
git pull fork master
git push
~~~

Now we can run everything from `/opt/coldfront_app/portal` in the accounts volume at `opt_accounts`.

<a id="setup-latest"></a>
## Setup notes [2020.09.04] 

These instructions will set up a testing environment so you can use all three components at once (SLURM, LDAP, Coldfront). After you complete these instructions, portal development can continue at the portal repository at [`https://github.com/marcc-hpc/portal`](https://github.com/marcc-hpc/portal).

~~~
git clone https://github.com/bradleyrp/factory -b bluecrab
cd factory
./fac use specs/cli_replicator.yaml
make -C specs/slurm-docker stop
make -C specs/slurm-docker clean # this erases volumes so be careful
make -C specs/slurm-docker deepclean # this erases images so be careful
make -C specs/slurm-docker make_volumes
make -C specs/slurm-docker build
# build containers
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_build rebuild
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_ldap_build rebuild
# command to start everything if volumes and containers are ready
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_combo
# shortcut to offline everything later
make down testcluster_combo
# onetime ldap database bootstrap. currently manual due to https://github.com/osixia/docker-openldap/issues/320
docker exec ldap ldapadd -Z -D "cn=admin,dc=rockfish,dc=intern" -w "test1234" -f "/container/service/slapd/assets/config/bootstrap/ldif/custom/bootstrap.ldif"
# ontime coldfront deployment in a persistent opt_accounts container
docker exec -it accounts bash
cd /opt
mkdir coldfront_app
cd coldfront_app
# we forked coldfront privately to continue development
# you may need to get permission to access this repository
# note that ALL PORTAL development will proceed from this repo
# changes to the factory required for testing can be sent to ryan
# later we should set up a shared fork of the factory code
git clone https://github.com/marcc-hpc/portal -b dev 
python3.8 -m venv venv
source venv/bin/activate
cd portal # or cd coldfront if you are just trying stock coldfront
pip install wheel
pip install -r requirements.txt
cp coldfront/config/local_settings.py.sample coldfront/config/local_settings.py
cp coldfront/config/local_strings.py.sample coldfront/config/local_strings.py
python manage.py initial_setup
python manage.py load_test_data
# startup the coldfront server
source /opt/coldfront_app/venv/bin/activate && cd /opt/coldfront_app/portal
python manage.py runserver 0.0.0.0:5000
# login as admin at http://localhost:5000/ with password "test1234"
~~~

<a id="ldap-interface"></a>
## LDAP Connections [2020.09.04]

In the instructions above we are tracking `marcc-hpc/portal` which has the following LDAP connections.

### Connect Coldfront to LDAP

In order to search for users in the LDAP database from coldfront, you must make the following changes to the config. Note that we have folded these changes into the private repository which tracks the portal development for our site.

~~~
diff coldfront/config/local_settings.py.sample coldfront/config/local_settings.py
182a183,189
> #! repetitive with above
> LDAP_SERVER_URI = 'ldap_server:389'
> LDAP_USER_SEARCH_BASE = 'dc=rockfish,dc=intern'
> LDAP_BIND_DN = 'cn=admin,dc=rockfish,dc=intern'
> LDAP_BIND_PASSWORD = 'test1234'
> ADDITIONAL_USER_SEARCH_CLASSES = ['coldfront.plugins.ldap_user_search.utils.LDAPUserSearch',]
~~~

### Use LDAP to authenticate

The feature above is useful because it allows us to query the LDAP database when adding users to a group. It would be even better to use LDAP to login directly that way *every single user* can log on to the system. The following changes to the settings will make this possible. Note the extra authentication is required, or you will get missing object errors.

~~~
import ldap
from django_auth_ldap.config import GroupOfNamesType, LDAPSearch

AUTH_LDAP_SERVER_URI = 'ldap://ldap_server'
#! possible site of a filter for PI so only certain PI can access things
AUTH_LDAP_USER_SEARCH_BASE = 'dc=rockfish,dc=intern'
AUTH_LDAP_START_TLS = False
AUTH_LDAP_BIND_AS_AUTHENTICATING_USER = False
AUTH_LDAP_MIRROR_GROUPS = False
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    AUTH_LDAP_USER_SEARCH_BASE, ldap.SCOPE_ONELEVEL, '(&(uid=%(user)s))')
AUTH_LDAP_GROUP_SEARCH_BASE = 'cn=groups,cn=accounts,dc=localhost,dc=localdomain'
AUTH_LDAP_GROUP_SEARCH_BASE = 'dc=rockfish,dc=intern'
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    AUTH_LDAP_GROUP_SEARCH_BASE, ldap.SCOPE_ONELEVEL, '(objectClass=groupOfNames)')
AUTH_LDAP_GROUP_TYPE = GroupOfNamesType()
AUTH_LDAP_USER_ATTR_MAP = {
    'username': 'uid',
    'first_name': 'givenName',
    'last_name': 'sn',
    'email': 'mail',
}
EXTRA_AUTHENTICATION_BACKENDS += ['django_auth_ldap.backend.LDAPBackend',]
#! trying to troubleshoot NO_SUCH_OBJECT errors
AUTH_LDAP_BIND_DN = 'cn=admin,dc=rockfish,dc=intern'
AUTH_LDAP_BIND_PASSWORD = 'test1234'
~~~

This avoids the process of having to set a password in LDAP admin.

### Forthcoming development

At this stage we have the following components in our development environment:

1. Docker containers with SLURM and LDAP servers.
2. An admin interface to LDAP and a way to prepopulate with data to simulate production.
3. A method for installing a privately-tracked Coldfront fork.
4. Settings which connect our Coldfront to the LDAP database in order to add users to a project.
5. Settings which also allow these users to authenticate directly with LDAP.

This project is designed to address three challenges on Rockfish: 

1. How do we add users and manage **users** on the system?
2. How can we manage **allocations** with SLURM?
3. How can we hold researchers accountable for **reporting** publications?

The components above are designed to address the allocations and reporting. We have included user management as a possible knock-on benefit because it might be easy to talk to the enterprise LDAP via some kind of bridge. More importantly, we require some method for representing users in order to complete the allocation and reporting interfaces. Hence the question of user management can be addressed in a *separate* application, or we can try to handle it internally. But for now, we will use LDAP to provide users for testing.

Ongoing development should answer the question of user management along with assistance from the systems team. One method for keeping user management and coldfront as modular as possible would be to include all users on the system in a special LDAP distinguished name or attribute that says whether they are part of the system.

## Portal development continues elsewhere

As of 2020.09.23 development of the portal itself has moved to a [private repository for our site](https://github.com/marcc-hpc/portal). The factory code will remain here for testing purposes, specifically as we populate an LDAP database to simulate a production environment. Further testing instructions will be tracked in this readme until this code is added to integration tests for the final product.

*The instructions [above](#setup-latest) will help you set up the development environment for the portal until we move it to the cluster itself. Changes to the factory required for testing should go to Ryan Bradley or we can fork this repo later. 

## Return to development for backups

After starting deployment on the `rockfish` branch on a coldfront VM on the new cluster, we returned to this development environment to handle backups and testing. We switched to the `rockfish` branch in our local development environment (instead of using the `dev` branch) and added postgresql to the compose orchestration. 

### Onetime setup

The following was required for one-time setup.

~~~
# step 1: run the server automatically for usability 
# made an entrypoint that starts slurmd and the coldfront server instead of doing this manually with docker exec
# however note that you might want to do development the usual way by changing the command for the accounts container in testcluster_combo
# if you introduce a syntax error the container will crash out so sometimes manually starting the server is better
# when setting this up we edited the script in the container
docker run -it --rm -v opt_accounts:/opt centos:centos7 bash
vi /opt/coldfront_app/portal/coldfront/config/dev_entry.sh
# step 2: update the container with postgres
# see changes to marcc-hpc.yaml at commit: [bluecrab 749ab65] added postgresql
# if you run coldfront here then you will experience the pg_config error
# normally I would rebuild the container here, but we would have to add an entire postgresql server
#   and this would defeat the entire purpose of having it in a docker
#   instead I switched to the binary version in pip since the backup system does not care about performance
# make a new requirements file and change to psycopg2-binary
docker run -it --rm -v opt_accounts:/opt marcc-hpc:testcluster bash
cd /opt/coldfront_app/portal/
source ../venv/bin/activate
# save the current docker requirements in case we break them
cp requirements.txt requirements_dev.txt
pip freeze > requirements_2021.01.04.0730_dev.txt
pip install -r requirements_dev.txt
pip freeze > requirements_2021.01.04.0740_dev.txt
~~~

### Starting the development server

After onetime configuration, start up the development and backup system with the following procedure. Added a new `COLDFRONT_MODE` variable to set the settings files.

~~~
# ryan laptop
cd ~/worker/dev/factory
# make sure you have the correct branch for this
git checkout bluecrab
# start everything up
make docker specs/slurm-docker/marcc-hpc.yaml testcluster_combo
# for manual development change the command for the accounts container to slurmd from dev_entry.sh in marcc-hpc.yaml
# if this command uses the dev_entry script then the server should be ready without these steps
docker exec -it accounts bash
cd /opt/coldfront_app/portal/
source ../venv/bin/activate
COLDFRONT_MODE=dev python manage.py runserver 0.0.0.0:5000 
~~~

### Resetting the development server

Use these instructions to reset the dev server and restore the initial data set. Portions of this instruction set can be used in production.

~~~
# follow the instructions above to start everything up
# option: totally nuke postgres
make down testcluster_combo  
docker volume ls
# remove all stopped containers
docker rm $(docker ps -a -q)
docker volume rm var_lib_postgres
docker volume create --name=var_lib_postgres
# step 1: delete things inside of postgres
# make sure everything is started per above
docker exec -it postgres bash
su postgres
dropdb coldfront_prime
psql -c "drop role if exists coldfront;"
createdb coldfront_prime
# note here and below we are recommending a password that will be committed to github; the real one should be stored in the secrets file
psql -c "CREATE ROLE coldfront WITH LOGIN PASSWORD 'rockfishnewcluster'; GRANT ALL PRIVILEGES ON DATABASE coldfront_prime TO coldfront;"
# exit and populate things for django
# step 2: kickstart django
docker exec -it accounts bash
cd /opt/coldfront_app/portal/
source ../venv/bin/activate
export COLDFRONT_MODE=dev
# setup the database
python manage.py initial_setup
# load the initial data (if desired)
python manage.py load_test_data
# start the application
COLDFRONT_MODE=dev python manage.py runserver 0.0.0.0:5000
# step 3: dump everything to postgresql
docker exec -it postgres bash
# dump the data into the postgresql volume
su - postgres -c "pg_dump coldfront_prime" > /var/lib/postgresql/data/initial_eg_database.psql
# step 4: load this data (or data from the production server)
docker exec -it postgres bash
su postgres
dropdb coldfront_prime
psql -c "drop role if exists coldfront;"
createdb coldfront_prime
psql -c "CREATE ROLE coldfront WITH LOGIN PASSWORD 'rockfishnewcluster'; GRANT ALL PRIVILEGES ON DATABASE coldfront_prime TO coldfront;"
psql coldfront_prime < /var/lib/postgresql/data/initial_eg_database.psql
# some of this may be redundant if you already ran initial_setup above, but if you have extra data it will slurp it up
~~~

### Superuser

In production we will avoid using the example data. Admins will first login via LDAP but we need a method for promoting them to superusers. Make a single secret superuser here. Use `python manage.py createsuperuser`.

