from __future__ import unicode_literals

from django.db import models
from django.conf import settings

import os,sys,re,shutil
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

class SimulationQuerySet(models.QuerySet):
	"""
	Must accompany the custom delete in the model for bulk deletion.
	Be sure to add "objects = SimulationQuerySet.as_manager()" to the target class.
	"""
	def delete(self,*args,**kwargs):
		for obj in self: obj.delete()
		super(SimulationQuerySet,self).delete(*args,**kwargs)

class Simulation(models.Model):
	"""
	A simulation executed by automacs.
	"""
	objects = SimulationQuerySet.as_manager()
	class Meta:
		verbose_name = 'AMX simulation'
	name = models.CharField(max_length=100,unique=True)
	path = models.CharField(max_length=100,unique=True)
	experiment = models.CharField(max_length=100,blank=True)
	kickstart = models.CharField(max_length=100,blank=True)
	status = models.CharField(max_length=100,blank=True)
	def __str__(self): return self.name

	def delete(self):
		"""
		Remove the simulation directory via the admin page.
		"""
		print('[STATUS] deleting simulation %s'%self.path)
		#---removed exception if the code is blank and now allow deletion even if no folder
		if re.match('^\s*$',self.path) or not os.path.isdir(os.path.join(settings.SIMSPOT,self.path)):
			print('[WARNING] that simulation cannot be found or deleted (path="%s")'%self.path)
		else: shutil.rmtree(os.path.join(settings.SIMSPOT,self.path))
		print('[STATUS] done')
		super(Simulation,self).delete()

class Kickstart(models.Model):
	"""
	A text block of commands that "kickstarts" an automacs simulation.
	"""
	class Meta:
		verbose_name = 'AMX kickstarter'
	name = models.CharField(max_length=100,unique=True)
	text = models.TextField(unique=True)
	def __str__(self): return self.name

def validate_file_extension(value):
	if not re.match(r'^.+\.pdb$',value):
		raise ValidationError(_('%(value)s requires a file extension'),params={'value':value},)

class CoordinatesQuerySet(models.QuerySet):
	"""
	Must accompany the custom delete in the model for bulk deletion.
	Be sure to add "objects = CoordinatesQuerySet.as_manager()" to the target class.
	"""
	def delete(self,*args,**kwargs):
		for obj in self: obj.delete()
		super(CoordinatesQuerySet,self).delete(*args,**kwargs)

class Coordinates(models.Model):
	"""
	A starting structure for a simulation.
	"""
	objects = CoordinatesQuerySet.as_manager()
	class Meta:
		verbose_name = 'AMX coordinates'
	name = models.CharField(max_length=100,unique=True,validators=[validate_file_extension])
	source_file_name = models.CharField(max_length=100)
