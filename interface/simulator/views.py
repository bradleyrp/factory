from __future__ import unicode_literals
from django.http import HttpResponse,HttpResponseRedirect
from django.shortcuts import render,get_object_or_404
from django.template import loader
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse
from .forms import *
from .models import *
from .interact import *
from .tools import import_remote
import os,json,glob

from calculator.interact import get_notebook_token

# hold globals which should never change
#! is this method sound?
notebook_token = None

#---! this is a useful tool. move it somewhere more prominent
#---dictionary lookups in templates e.g. "status_by_sim|get_item:sim.name"
from django.template.defaulttags import register
@register.filter
def get_item(dictionary,key): return dictionary.get(key)

# fieldsets to organize the parts of a form
from django.forms.forms import BoundField
class FieldSet(object):
    def __init__(self,form,fields,legend='',cls=None,details=''):
        self.form = form
        self.legend = legend
        self.details = details
        self.fields = fields
        self.cls = cls
    def __iter__(self):
        for name in self.fields:
            field = self.form.fields[name]
            yield BoundField(self.form, field, name)

def index(request):
	"""
	Simulator index shows: simulations, start button.
	"""
	global notebook_token
	#---get the notebook token once and hold it in memory
	if not notebook_token: notebook_token = get_notebook_token()
	print(settings.GROMACS_CONFIG)
	sims = Simulation.objects.all().order_by('id')
	coords = Coordinates.objects.all().order_by('id')
	outgoing = dict(sims=sims,coords=coords,notebook_token=notebook_token)
	outgoing.update(root=settings.SIMSPOT)
	#---simulations by status
	statuses = job_status_infer()
	cluster_stat = dict([(stat_type,[{'name':name,'id':stat['id']} 
		for name,stat in statuses.items() if stat['stat']==stat_type])
		for stat_type in ['running','waiting','finished']])
	outgoing.update(cluster_stat=cluster_stat)
	statuses_by_sim = dict([(k,v['stat'] if v['stat'] else '???XXXX') for k,v in statuses.items()])
	outgoing.update(status_by_sim=statuses_by_sim)
	#---hide the cluster console unless some jobs are running
	if any(v=='running' for v in statuses_by_sim.values()): outgoing.update(cluster_running=True)

	if request.method == 'GET': 
		form = build_simulation_form()
		form_upload_coords = build_form_upload_coords()
		outgoing.update(form_sim_new=form,form_upload_coords=form_upload_coords)
		return render(request,'simulator/index.html',outgoing)
	#---if you end up here, it's because you are starting a simulation
	else:
		form = build_simulation_form(request.POST,request.FILES)
		#---note the following forms are empty because index POST handles simulatins
		form_upload_coords = build_form_upload_coords()
		outgoing.update(form_sim_new=form,form_upload_coords=form_upload_coords)
		#---index POST handles new simulations. other forms are routed to their respective functions
		if form.is_valid():
			sim = form.save(commit=False)
			sim.path = re.sub(' ','_',sim.name)
			sim.status = 'created'
			sim.save()
			prepare_simulation(sim)
			return HttpResponseRedirect(reverse('simulator:detail_simulation',kwargs={'id':sim.id}))
	return render(request,'simulator/index.html',outgoing)

def job_status_infer(sim=None):
	"""
	Look at the cluster to infer the job statuses.
	"""
	regex_submitted = '^submitted:(.+)$'
	#---if no stamp is supplied, we get them from simulation statuses
	if not sim: 
		sims = Simulation.objects.all().order_by('id')
		sims_submitted = [sim for sim in sims if re.match(regex_submitted,sim.status)]
		sims_stamps = dict([(sim.name,re.match(regex_submitted,sim.status).group(1)) 
			for sim in sims_submitted])
		sims_not_submitted = [sim for sim in sims if not re.match(regex_submitted,sim.status)]
	else: sims_submitted,sims_not_submitted = [sim],[]
	#---infer the status of each job
	statuses = {}
	for sim in sims_submitted:
		if not re.match(regex_submitted,sim.status): continue
		job_status = 'idle'
		#---if the job is submitted we have to run this refresh block to infer its status
		#---! is inference the best option here, or should we track the jobs in the database?
		#---pop off the submission path
		submit_stamp = re.match('^submitted:(.+)$',sim.status).group(1)
		#---anticipate different names for the file depending on its job status
		for namer,form in settings.CLUSTER_NAMER.items():
			job_cluster_fn = os.path.join(settings.CLUSTER,re.sub('STAMP',submit_stamp,form))
			if os.path.isfile(job_cluster_fn):
				job_status = namer
				break
		statuses[sim.name] = {'stat':job_status,'stamp':submit_stamp,'fn':job_cluster_fn,'id':sim.id}
	for sim in sims_not_submitted:
		statuses[sim.name] = {'stat':'construction',
			'stamp':'no stamp yet','fn':'no job file yet','id':sim.id}
	return statuses

def detail_simulation(request,id):
	"""
	Detailed view of a simulation with tuneable parameters if the job is not 
	yet submitted.
	"""
	# it is rare but possible to get to a simulation detail without a token
	global notebook_token
	# get the notebook token once and hold it in memory
	if not notebook_token: notebook_token = get_notebook_token()

	sim = get_object_or_404(Simulation,pk=id)
	spot = os.path.join(settings.SIMSPOT,sim.path)
	outgoing = dict(sim=sim,notebook_token=notebook_token)

	config = ortho.read_config(source=os.path.join(spot,'config.json'))
	outgoing.update(config=config)
	
	# if created by not kickstarted then we choose a kickstarter
	if sim.status=='created':
		kickstarts = config.get('kickstarters',{})
		if not kickstarts: 
			raise Exception('cannot find kickstarers in the config for %s'%spot)
		outgoing.update(kickstarts=kickstarts)
		for key,val in kickstarts.items(): 
			Kickstart.objects.get_or_create(name=key)#!?,text=val.strip
		kickstarts = Kickstart.objects.all().order_by('id')
		outgoing.update(kickstarts=kickstarts)

	# get the preplist but only if we have kickstarted
	if sim.status=='kickstarted':
		preptext = bash('make prep json=True',
			cwd=settings.SIMSPOT+sim.path,scroll=False)
		# standard syntax for getting json
		regex_json_get = r'json:(.+)$'
		expts = json.loads(re.search(regex_json_get,
			preptext['stdout'],flags=re.M+re.DOTALL).group(1))
		#! currently only works for run
		#! for key in ['quick']: del
		outgoing.update(expts={'collected':expts['sources'].items()})

	# after kickstart and prepping the experiment we are now ready to customize
	if sim.status=='selected_expt':
		# options above instantiated by links and refreshes. below we use forms
		if request.method=='GET':
			outgoing.update(status='kickstarted with "%s" and prepared experiment "%s"'%
				(sim.kickstart,sim.experiment))
			settings_blocks = {}
			run_expt_fn = os.path.join(settings.SIMSPOT,sim.path,'expt.json')
			run_expts = sorted(glob.glob(os.path.join(settings.SIMSPOT,sim.path,'expt_*.json')),
				key=lambda x:int(re.match(r'^expt_(.+)\.json$',os.path.basename(x)).group(1)))
			# checking for expt.json will help determine if this is a metarun
			#! is this strict enough?
			if run_expts!=[] and os.path.isfile(run_expt_fn):
				raise Exception(
					'found expt.json and %s hence this appears to be both a run and metarun'%run_expts)
			# process a run
			elif os.path.isfile(run_expt_fn):
				with open(run_expt_fn) as fp:
					expt = json.load(fp)
					outgoing.update(settings_raw=expt['settings'])
				# a single settings block for a standard run
				settings_blocks = {'settings':{'settings':expt['settings'],
					'multi':[i[0] for i in expt['settings']]+['mdp_specs']}}
			elif run_expts!=[]:
				settings_blocks = {}
				# parse each JSON experiment file and add to outgoing
				#! note that because of the fieldsets in the template the steps might be out of order
				#!   however this is difficult to fix. it will require a filter.
				for mnum,fn in enumerate(run_expts):
					with open(fn) as fp:
						expt = json.load(fp)
						outgoing.update(**{'settings_raw_%d'%mnum:str(yamlb(expt['settings']))})
					raise Exception(expt['settings'])
					settings_blocks['settings, step %d'%(mnum+1)] = {
						'settings':yamlb(expt['settings']),
						'multi':[i[0] for i in expt['settings']]+['mdp_specs']}
			else: raise Exception('failed to find the correct experiment JSON files')
			form = SimulationSettingsForm(initial={'settings_blocks':settings_blocks})
			# prepare fieldsets as a loop over the blocks of settings, one per run
			outgoing['fieldsets'] = [FieldSet(form,[settings_name+'|'+key 
				for key,val in settings_block['settings'].items()],legend=settings_name) 
				for settings_name,settings_block in settings_blocks.items()]
			#! add a condition for whether we need a coordinate here? only some methods actually use it
			form_source = CoordinatesSelectorForm()
			outgoing['fieldsets'].append(FieldSet(form_source,['source'],
				legend="coordinates"))
			outgoing['fieldsets'] = tuple(outgoing['fieldsets'])
		# on submission we prepare the job
		else:
			form = SimulationSettingsForm(request.POST,request.FILES)
			form_source = CoordinatesSelectorForm(request.POST,request.FILES)
			# note that the form validator applies here. Using "None" in the settings will cause some 
			#   settings to be blank on the form and excepted on post. use "none" to get around this
			# note that if the form is invalid the site will complain and keep you there
			if form.is_valid() and form_source.is_valid():
				if 'method_auto' in request.POST:
					# unpack the form
					unpacked_form = [(i.split('|'),j) for i,j in form.data.items() if '|' in i]
					settings_blocks = dict([(k[0],{}) for k,v in unpacked_form])
					for (run_name,key),val in unpacked_form: settings_blocks[run_name][key] = val
					# note that a one-block run is a standard run (not a metarun)
					if len(settings_blocks)==1:
						submit_fn = make_run(expt=settings_blocks['settings'],cwd=sim.path)
					else: 
						submit_fn = make_metarun(expt=settings_blocks,cwd=sim.path)
					sim.status = 'submitted:%s'%submit_fn
					sim.save()
					#!!! under construction
					if False:
						# process any incoming sources
						pks = form_source.cleaned_data['source']
						#! implement input folders here at some point, perhaps using an alternate data structure
						if len(pks)>=1:
							if len(pks)>1:
								return HttpResponse('cannot parse incoming coordinates request: %s'%
									str(form_source.cleaned_data))
							obj = Coordinates.objects.get(pk=pks[0])
							# copy the coordinate to the automacs simulation, where it is automatically picked up
							# ... from the root of the inputs folder (assume no other PDB file there)
							shutil.copyfile(os.path.join(settings.COORDS,obj.name),
								os.path.join(settings.SIMSPOT,sim.path,'inputs',obj.name))
					return HttpResponseRedirect(reverse('simulator:detail_simulation',kwargs={'id':sim.id}))
				elif 'method_manual' in request.POST:
					"""
					By this point, clicking the experiment button has run `make prep` and the simulation
					has the scripts and json files ready. To customize in IPython, then, we only need to
					read the expt JSON files and scripts and put them into an interactive notebook and then
					change the simulation state to note that we are now off-pathway.
					"""
					export_notebook_simulation(sim)
					return HttpResponseRedirect(reverse('simulator:detail_simulation',kwargs={'id':sim.id}))
				else: raise Exception('button failure')

	# submitted and running jobs
	if re.match('^submitted:.+$',sim.status):
		statuses = job_status_infer(sim=sim)
		outgoing.update(job_status=statuses[sim.name]['stat'])
		# only show the ajax console if we are running
		if statuses[sim.name]['stat']=='running':
			outgoing.update(logging=os.path.basename(statuses[sim.name]['fn']))

	if sim.status=='manual_interactive_run':
		fn = os.path.relpath(os.path.join(settings.SIMSPOT,sim.path,'simulation.ipynb'),os.getcwd())
		outgoing.update(manual_interactive_state=fn)

	print('yo sim status is')
	print(sim.status)

	# submitted and running jobs
	if re.match('^submitted:.+$',sim.status):
		job_status = None
		# if the job is submitted we have to run this refresh block to infer its status
		#! is inference the best option here, or should we track the jobs in the database?
		# pop off the submission path
		submit_stamp = re.match('^submitted:(.+)$',sim.status).group(1)
		# anticipate different names for the file depending on its job status
		for namer,form in settings.CLUSTER_NAMER.items():
			if os.path.isfile(os.path.join(settings.CLUSTER,re.sub('STAMP',submit_stamp,form))):
				job_status = namer
				#! best not to update the job status here because otherwise we cannot refresh
				break
		outgoing.update(job_status=job_status)

	# outgoing request only shows the user things they can change
	return render(request,'simulator/detail.html',outgoing)

def upload_coordinates(request):
	"""
	Upload files to a new external source which can be added to future simulations.
	"""
	if request.method == 'GET': 
		form_coords = build_form_upload_coords()
	else:
		form_coords = build_form_upload_coords(request.POST,request.FILES)
		if form_coords.is_valid():
			coords = form_coords.save(commit=False)
			coords.name = re.sub(' ','_',coords.name)
			#---! do other stuff here if you want, before saving
			for filedat in request.FILES.getlist('files'):
				#---assume only one file and we save the name here
				coords.source_file_name = filedat.name
				with open(os.path.join(settings.COORDS,coords.name),'wb+') as fp:
					for chunk in filedat.chunks(): fp.write(chunk)
			coords.save()
			return HttpResponseRedirect('/')
	#---! this is kind of wasteful because index already does it ???
	outgoing = dict(sims=Simulation.objects.all().order_by('id'),\
		coords=Coordinates.objects.all().order_by('id'))
	outgoing.update(root=settings.SIMSPOT)
	form = build_simulation_form()
	outgoing.update(form_sim_new=form,form_upload_coords=form_coords)
	return render(request,'simulator/index.html',outgoing)

def cluster_view(request,debug=False):
	"""
	Report on a running simulation if one exists.
	"""
	#---! hacked six ways
	#---! NOTE THAT WE WANT ALL FILE MONITORING TO HAVE SOME KIND OF CHANGE-PUSH METHOD INSTEAD OF FREQUENT
	#---! ...CALLS TO DJANGO, WHICH SEEMS SILLY.
	try:
		with open('logs/%s.cluster'%settings.NAME) as fp: text = fp.read()
		return JsonResponse({'line':text,'running':True})
	except: return JsonResponse({'line':'idle','running':False})

def sim_console(request,log_fn):
	"""
	Report on a running simulation if one exists.
	Note that getting teh status of the simulation automatically provides the filename for the running
	job's log file. Hence we send the log file as a signal to monitor things, then send it back through
	the URL so that the sim_console function (me) needs only to pipe it back to the page. This is 
	way more elegant than using this function to request the file, since we already have it in the detail
	function.
	"""
	#---! hacked six ways
	try:
		with open(os.path.join(settings.CLUSTER,log_fn)) as fp: text = fp.read()
		return JsonResponse({'line':text,'running':True})
	except: return JsonResponse({'line':'idle','running':False})

def export_notebook_simulation(sim,tab_width=4):
	"""
	Convert a plot script into an interactive notebook.
	Moved this from interact.py for access to shared_work.
	"""
	cwd = os.path.join(settings.SIMSPOT,sim.path)
	target_notebook = os.path.join(cwd,'simulation.ipynb')
	if os.path.isfile(target_notebook):
		raise Exception('development: redirect to %s'%target_notebook)

	# assume that we have done `make prep` to arrive here hence the expt_N.json and script_N.json files
	# ... are ready to go. we simply intervene to change to an interactive notebook
	fn_register = {}
	for base,suffix in [('script','py'),('expt','json')]:
		fns = map(lambda x:os.path.basename(x),glob.glob(os.path.join(cwd,'%s*.%s'%(base,suffix))))
		singleton = '%s.%s'%(base,suffix)
		if singleton in fns and len(fns)!=1: raise Exception('invalid files: %s'%fns)
		elif fns==[singleton]: 
			fn_register[base] = fns
			fn_register['%s_indices'%base] = None
		else: 
			key_by = lambda x:int(re.match('^%s_(\d+)\.%s$'%(base,suffix),x).group(1))
			fn_register[base] = sorted(fns,key=key_by)
			fn_register['%s_indices'%base] = sorted(map(key_by,fns))
	if fn_register['script_indices']!=fn_register['expt_indices']: 
		raise Exception('invalid files: %s'%fn_register)
	mode = 'run' if fn_register['expt_indices']==None else 'metarun'

	stamp = datetime.datetime.now().strftime('%Y.%m.%d.%H%M.%S')
	useful_info = {'root':os.path.abspath(cwd),'stamp':stamp,'name':sim.name,'experiment':sim.experiment,
		'experiment_fns':', '.join([str(i) for i in fn_register['expt']]) 
		if fn_register!=None else ['expt.json']}

	note_flow = ("""## instructions\n
	All simulations start from an experiment file (matching `*_expts.py`). 
	If you arrived here from the factory-simulator page, you have already chosen an experiment 
	which has been written to disk in JSON format (`%(experiment_fns)s`). 
	The following interactive script has two sections.\n
	1. The "experiment file" section lets you customize and then re-write the experiment files to disk.
	2. The "simulation script" section contains the Python script(s) which run the simulations.\n
	If you encounter errors, you can start from scratch in a new cell via: 
	`! make clean sure && make prep %(experiment)s`\n
	The simulation is stored at: `%(root)s`\n
	"""%useful_info)

	import nbformat as nbf
	# make a new notebook
	nb = nbf.v4.new_notebook()
	header_text = ('\n\n'.join(["# `%(name)s`",
		'*an AUTOMACS simulation*','Generated from the `%(experiment)s` experiment.',
		'Generated on: `%(stamp)s`','Data are saved at: `%(root)s`']))%useful_info
	nb['cells'].append(nbf.v4.new_markdown_cell(header_text))
	nb['cells'].append(nbf.v4.new_markdown_cell(re.sub('\t','',note_flow)))
	for snum,(script,expt) in enumerate(zip(fn_register['script'],fn_register['expt'])):
		if mode=='metarun': 
			nb['cells'].append(nbf.v4.new_markdown_cell('## experiment settings: step %d'%snum))
		elif mode=='run': nb['cells'].append(nbf.v4.new_markdown_cell('## experiment settings'))
		else: raise Exception
		with open(os.path.join(cwd,expt)) as fp: expt_raw = json.loads(fp.read())
		rewrite_seq = [
			'import os,json',
			'with open(\'%s\') as fp: expt = json.loads(fp.read())'%expt,
			'expt.update(settings=settings_%s)'%re.sub('\.json','',expt),
			'with open(\'%s\',\'w\') as fp: fp.write(json.dumps(expt))'%expt,]
		nb['cells'].append(nbf.v4.new_code_cell(
			'settings_%s = """%s"""\n\n'%(re.sub('\.json','',expt),expt_raw['settings'])+
			'\n'.join(rewrite_seq)))
	for snum,(script,expt) in enumerate(zip(fn_register['script'],fn_register['expt'])):
		if mode=='metarun': 
			nb['cells'].append(nbf.v4.new_markdown_cell('## simulation script: step %d\n\n'%snum+
				'note: you can run this script here, or in the terminal via "`python script_%d.py`"'%snum))
		elif mode=='run': 
			nb['cells'].append(nbf.v4.new_markdown_cell('## simulation script\n\n'+
				'note: you can run this script here, or in the terminal via `python script.py`'))
		else: raise Exception
		# write the script
		with open(os.path.join(cwd,script)) as fp: script_text = fp.read()
		if mode=='metarun': 
			script_text_mod = '%s\n%s\n%s'%(
				'import shutil\nshutil.copyfile(\'%s\',\'%s\')'%(
				expt,'expt.json'),re.sub('#!/usr/bin/env python\n+','',script_text.strip(),re.M),
				'print(\'[STATUS] complete!\')')
			nb['cells'].append(nbf.v4.new_code_cell(re.sub('\t',' '*tab_width,script_text_mod)))
		elif mode=='run': 
			script_text_mod = '%s\n%s'%(
				script_text.strip(),'print(\'[STATUS] complete!\')')
			nb['cells'].append(nbf.v4.new_code_cell(re.sub('\t',' '*tab_width,script_text_mod)))
		else: raise Exception
	# write the notebook
	with open(os.path.join(cwd,target_notebook),'w') as fp: nbf.write(nb,fp)
	sim.status = 'manual_interactive_run'
	sim.save()
