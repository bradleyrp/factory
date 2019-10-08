#!/usr/bin/env python

# ./fac envrun python dev.py
import ortho
import time
ortho.queue.simple_queue.simple_task_queue()
time.sleep(2)
ortho.queue.simple_queue.launch('echo 123 && sleep 10 && echo 456')
#ortho.queue.simple_queue.launch('. spack/share/spack/setup-env.sh && cd spack/std_env && spack install > ../../log-spack-install 1>&2')
ortho.queue.simple_queue.launch('make do specs/spack_gromacs.yaml')
ortho.queue.simple_queue.launch('echo 123x && sleep 30 && echo 456x')
