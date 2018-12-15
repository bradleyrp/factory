from django.http import HttpResponse,HttpResponseRedirect
from django.shortcuts import render,get_object_or_404,redirect
from django.template import loader
#! deprecated from django.core.urlresolvers import reverse
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse
from .models import *
import nbformat as nbf

from .interact import make_bootstrap_tree,get_notebook_token
from .interact import FactoryWorkspace,PictureAlbum,FactoryBackrun
from .tools import bash

import os,json,re,datetime,time,glob,pprint,subprocess,yaml,copy

#---shared global variables to prevent lags
shared_work = None
shared_album = None
shared_backrun = None
notebook_token = None

###---START WORKSPACE TILES

def make_tree_postdat(outgoing):
	"""Present post-processing data as a tree for the index."""
	global shared_work
	#---collect posts by basename, excluding the numbered part of the filenames
	try: posts = shared_work.work.postdat.posts()
	except: return HttpResponse(str(shared_work))
	base_names = sorted(set(map(lambda x:re.match('^(.*?)\.n',x).group(1),posts.keys())))
	short_names = sorted(set([v.specs['slice']['short_name'] for k,v in posts.items()]))
	posts_restruct = {}
	for sn in short_names:
		keys = [p for p,v in posts.items() if v.specs['slice']['short_name']==sn]
		base_names = sorted(set(map(lambda x:re.match('^(.*?)\.n',x).group(1),keys)))
		#---! note that we might also want to organize the postdata by short_name
		posts_restruct[sn] = dict([(b,
			dict([(k,posts[pname]) for k in 
			[pname for pname in posts.keys() if re.match('^%s'%b,pname)]
			])) for b in base_names])
	posts_tree = json.dumps(list(make_bootstrap_tree(posts_restruct,floor=2)))
	outgoing['trees']['posts'] = {'title':'postprocessing data',
		'name':'posts','name_tree':'posts_tree','data':posts_tree}

def make_tree_slices(outgoing):
	"""Make a slices tree."""
	#---! removed for compatibility with omnicalc development branch
	return False
	global shared_work
	if shared_work.work.slices: slices_tree = json.dumps(
		list(make_bootstrap_tree(shared_work.work.slices,floor=3)))
	else: slices_tree = json.dumps({})
	outgoing['trees']['slices'] = {'title':'slices',
		'name':'slices','name_tree':'slices_tree','data':slices_tree}

def make_tree_calculations(outgoing):
	"""Expose workspace calculations as a tree."""
	global shared_work
	if shared_work.work.metadata.calculations:
		#---! high floor for compatibility with omnicalc development branch
		calcs_tree_raw = list(make_bootstrap_tree(shared_work.work.metadata.calculations,floor=10))
	else: calcs_tree_raw = []
	for cc,c in enumerate(calcs_tree_raw): calcs_tree_raw[cc]['href'] = 'get_code/%s.py'%c['text']
	calcs_tree = json.dumps(calcs_tree_raw)
	outgoing['trees']['calcs'] = {'title':'calculations',
		#!!!!!!!!!!!! RYAN THIS IS BROKEN FIX IT
		'name':'calcs','name_tree':'calcs_tree','data':json.dumps([])}

def make_tree_plots(outgoing):
	"""Present plots as a tree."""
	global shared_work
	#! legacy mode is being refactored here
	if False:
		#---plots can come from a few different places: the plots dictionary, a plot file, or an interactive 
		#---...notebook which comes from a plot script. note that plot items which are not found in the calcs
		#---...folder will throw an error message
		#---start with the plots in the workspace
		plots_assembled = copy.deepcopy(shared_work.work.metadata.plots)
		for plotname,plot in plots_assembled.items():
			plot_fn = os.path.join(settings.CALC,'calcs','plot-%s.py'%plotname)
			if not os.path.isfile(plot_fn):
				plots_assembled[plotname] = {'details':copy.deepcopy(plot),
					'ERROR missing plot script!':('this plot is not found in %s'
					'however it is listed in the plots section of the metadata')%plot_fn}
			else: plots_assembled[plotname] = {'details':copy.deepcopy(plot)}
			plot_fn_interact = os.path.join(settings.CALC,'calcs','plot-%s.ipynb'%plotname)
			if os.path.isfile(plot_fn_interact):
				plots_assembled[plotname][os.path.basename(plot_fn_interact)] = (
					'interactive plot generated on (UTC) %s'%
					datetime.datetime.fromtimestamp(os.path.getmtime(plot_fn_interact)))
		#---catch any plots not in the workspace
		for fn in glob.glob(os.path.join(settings.CALC,'calcs','plot-*.py')):
			plotname = re.match('^plot-(.+)\.py$',os.path.basename(fn)).group(1)
			if plotname not in plots_assembled:
				plots_assembled[plotname] = {'note: default plot':'this plot was found on disk but it has no '
				'entry in the metadata. when it runs, it will use the corresponding entry from the `calculation` '
				'entry in the metadata to figure out which simulations to plot.'}
				#---! repetitive. add the interactive notebook if it's there
				plot_fn_interact = os.path.join(settings.CALC,'calcs','plot-%s.ipynb'%plotname)
				if os.path.isfile(plot_fn_interact):
					plots_assembled[plotname][os.path.basename(plot_fn_interact)] = (
						'interactive plot generated on (UTC) %s'%
						datetime.datetime.fromtimestamp(os.path.getmtime(plot_fn_interact)))
	# plots come directly from the FactoryWorkspace
	plots_assembled = dict([(k,k) for k in shared_work.plot_scripts])
	#! omnicalc dev branch note. need lower levels or the bootstrap chokes
	plots_tree_raw = list(make_bootstrap_tree(plots_assembled,floor=4))
	# sorting by top-level keys
	plots_tree_raw = sorted(plots_tree_raw,key=lambda x:x['text'])
	for cc,c in enumerate(plots_tree_raw): 
		#---suppress links if the file is missing. note the error message above should help
		if os.path.isfile(os.path.join(settings.CALC,'calcs',c['text'])):
			plots_tree_raw[cc]['href'] = 'get_code/%s'%c['text']
		if os.path.isfile(os.path.join(settings.CALC,'calcs',re.sub('\.py$','.ipynb',c['text']))):
			try:
				#---get the right child index. since this is clumsy we only try
				ind_ipynb_link = [ii for ii,i in enumerate(plots_tree_raw[cc]['nodes']) 
					if re.match('^.+\.ipynb$',i['text'])][0]
				plots_tree_raw[cc]['nodes'][ind_ipynb_link]['href'] = 'http://%s:%s/%s?token=%s'%(
					settings.NOTEBOOK_IP,settings.NOTEBOOK_PORT,'/'.join([
					'tree','calc',settings.NAME,'calcs',re.sub('\.py$','.ipynb',c['text'])]),notebook_token)
			except: pass
	plots_tree = json.dumps(plots_tree_raw)
	outgoing['trees']['plots'] = {'title':'plots',
		'name':'plots','name_tree':'plots_tree','data':plots_tree}

def make_tree_tasks(outgoing):
	"""Present pending tasks as a tree."""
	global shared_work
	tasks_details = {}
	for name,task in shared_work.work.tasks:
		calc_name = task['post'].specs['calc']['calc_name']
		if calc_name not in tasks_details: tasks_details[calc_name] = {}
		sn = task['job'].sn
		tasks_details[calc_name][sn] = {
			'slice':task['job'].slice.__dict__,'calc':task['job'].calc.__dict__}
	tasks_tree_raw = list(make_bootstrap_tree(tasks_details,floor=3))
	for cc,c in enumerate(tasks_tree_raw):
		tasks_tree_raw[cc]['href'] = 'get_code/%s'%c['text']
	tasks_tree = json.dumps(tasks_tree_raw)
	outgoing['trees']['tasks'] = {'title':'pending calculations',
		'name':'tasks','name_tree':'tasks_tree','data':tasks_tree}

def make_tree_meta_files(outgoing):
	"""Make a list of meta files as a tree with links to edit the files."""
	global shared_work
	#---instead of using "shared_work.work.specs_files" we get all meta_files
	meta_fns = glob.glob(os.path.join(settings.CALC,'calcs','specs','*.yaml'))
	#---get meta files
	meta_files_rel = dict([(os.path.basename(k),os.path.relpath(k,os.path.join(os.getcwd(),settings.CALC))) 
		for k in meta_fns])
	meta_files_raw = list(make_bootstrap_tree(meta_files_rel,floor=1))
	for cc,c in enumerate(meta_files_raw):
		meta_files_raw[cc]['selectable'] = False
		meta_files_raw[cc]['href'] = 'http://%s:%s/%s?token=%s'%(
			settings.NOTEBOOK_IP,settings.NOTEBOOK_PORT,'/'.join([
			'edit','calc',settings.NAME,meta_files_rel[c['text']]]),notebook_token)
	meta_files_tree = json.dumps(meta_files_raw)
	#---! removed for compatibility with omnicalc development branch
	if False:
		meta_files_tree = json.dumps([{"text":os.path.basename(k),"nodes": []} 
			for k in shared_work.work.specs_files])
	outgoing['meta_files'] = dict([(os.path.basename(k),os.path.basename(k)) for k in meta_fns])
	outgoing['trees']['meta_files'] = {'title':'meta files',
		'name':'meta_files','name_tree':'meta_files_tree','data':meta_files_tree}

def make_warn_missings(outgoing):
	"""Warn the user if items are missing from meta."""
	#---! removed for compatibility with omnicalc development branch
	return False
	global shared_work
	#---! note that this should be modified so it is more elegant
	outgoing.update(missings=', '.join([i for i in 
		'slices calcs plots'.split() if not shared_work.work.__dict__[i]]))

###---END WORKSPACE TILES

def index(request,pictures=True,workspace=True,show_pictures=False):
	"""
	Simulator index shows: simulations, start button.
	"""
	global shared_work
	#---on the first visit we make the workspace
	if not shared_work: shared_work = FactoryWorkspace()
	#---catch post from compute button here
	if request.method=='POST':
		#---! note that the underscore transformation could be problematic
		#---! ...we cannot allow dots in the labels
		meta_fns_avail = glob.glob(os.path.join(settings.CALC,'calcs','specs','*.yaml'))
		meta_fns = dict([(os.path.basename(k),os.path.basename(k)) 
			for k in meta_fns_avail])
		if 'button_compute' in request.POST:
			#---checkboxes are only in the POST if they are checked
			return compute(request,meta_fns=[i for i in meta_fns if 'toggle_%s'%i in request.POST.keys()])
		elif 'button_refresh' in request.POST:
			return refresh(request,meta_fns=meta_fns)
		else: raise Exception('button failure')
	#---HTML sends back the status of visible elements so their visibility state does not change
	#---! needs replaced
	workspace = request.GET.get('workspace',
		{True:'true',False:'false','true':'true','false':'false'}[workspace])
	pictures = request.GET.get('pictures',
		{True:'true',False:'false','true':'true','false':'false'}[pictures])
	#---after this point workspace and picture flags are text
	#---send out variables that tell the HTML whether different elements (e.g. pictures) are visible
	#---! note that show_pictures could not be properly implemented on "only pictures"
	outgoing = {'trees':{},'workspace_visible':workspace,
		'pictures_visible':pictures,'show_pictures':show_pictures,
		'show_workspace_toggles':workspace=='true'}
	#---! deprecated: global work,workspace_timestamp,notebook_token,logging_state,logging_text,plotdat
	global shared_album,shared_backrun,notebook_token
	#---get the notebook token once and hold it in memory
	if not notebook_token: notebook_token = get_notebook_token()
	if not shared_backrun: shared_backrun = FactoryBackrun()
	outgoing.update(notebook_token=notebook_token)
	#---workspace view includes tiles that mirror the main items in the omnicalc workspace
	if workspace=='true':
		#---BEGIN POPULATING "outgoing"
		outgoing['found_meta_changes'] = shared_work.meta_changed()
		outgoing['workspace_timestamp'] = shared_work.timestamp()
		make_tree_postdat(outgoing)
		make_tree_slices(outgoing)
		make_tree_calculations(outgoing)
		make_tree_plots(outgoing)
		#---! currently testing on actinlink
		try: make_tree_tasks(outgoing)
		except: pass
		make_warn_missings(outgoing)
		make_tree_meta_files(outgoing)
		#---END POPULATING "outgoing"
		#---! use update method above instead of passing around the outgoing ...
		#---dispatch logging data
		outgoing.update(**shared_backrun.dispatch_log())
	#---if pictures are included in this view we send the album
	if pictures=='true':
		#---prepare pictures
		if not shared_album: shared_album = PictureAlbum(backrunner=shared_backrun)
		outgoing.update(album=shared_album.album)
	return render(request,'calculator/index.html',outgoing)

def refresh_thumbnails(request):
	"""Remake all thumbnails."""
	global shared_album
	print('REMAKING THUMBS!')
	shared_album = PictureAlbum(backrunner=shared_backrun,regenerate_all=True)
	print('DONE')
	return view_redirector(request)

def refresh(request,meta_fns=None):
	"""Refresh the workspace and redirect to the calculator."""
	# mimic the part of the compute section where we refresh metadata
	if meta_fns:
		bash('make unset meta_filter',cwd=settings.CALC,catch=True)
		bash('make set meta_filter %s'%' '.join(meta_fns),cwd=settings.CALC,catch=True)
	shared_work.refresh()
	return view_redirector(request)

def clear_stale(request):
	shared_work.clear_stale()
	shared_work.refresh()
	return view_redirector(request)

def get_code(request,name):
	"""Retrieve a calculation code."""
	global notebook_token
	if not notebook_token: notebook_token = get_notebook_token()
	outgoing = dict(plotname=name,notebook_token=notebook_token)
	# retrieve the raw code
	# switched to literal script names from previous versions
	path = os.path.join(settings.CALC,'calcs',name)
	with open(path) as fp: raw_code = fp.read()
	outgoing.update(raw_code=raw_code,path=os.path.basename(path))
	#---! legacy mode
	if False:
		#---detect an ipynb versions
		if re.match('^plot-(.+)',name):
			note_fn = os.path.relpath(os.path.join(settings.CALC,'calcs','%s.ipynb'%name),settings.FACTORY)
			if os.path.isfile(note_fn): outgoing.update(calc_notebook=os.path.basename(note_fn))
			else: outgoing.update(calc_notebook_make='MAKE')
	if name in shared_work.plot_scripts:
		note_fn = os.path.relpath(os.path.join(
			settings.CALC,'calcs',re.sub('\.py$','.ipynb',name)),settings.FACTORY)
		if os.path.isfile(note_fn): outgoing.update(calc_notebook=os.path.basename(note_fn))
		else: outgoing.update(calc_notebook_make='MAKE')
	return render(request,'calculator/codeview.html',outgoing)

def make_notebook(request,name):
	"""
	Redirect to the ipython notebook make function.
	"""
	#---extract the name by convention here
	export_notebook(name)
	#---naming convention on the redirect
	return HttpResponseRedirect(reverse('calculator:get_code',kwargs={'name':name}))

def export_notebook(plotname):
	"""
	Convert a plot script into an interactive notebook.
	Moved this from interact.py for access to shared_work.
	"""
	global shared_work
	header_code = '\n'.join(["plotname = '%s'","#---factory header",
		"exec(open('../omni/base/header_ipynb.py').read())"])
	cwd = settings.CALC
	target = 'calcs/%s'%plotname
	dest = 'calcs/%s'%re.sub('\.py$','.ipynb',plotname)
	regex_splitter = r'(\n\#[-\s]*block:.*?\n|\n%%.*?\n)'
	regex_hashbang = r'^\#.*?\n(.+)$'
	#---all tabs are converted to spaces because Jupyter
	tab_width = 4
	#---make a new notebook
	nb = nbf.v4.new_notebook()
	#---read the target plotting script
	with open(os.path.join(cwd,target)) as fp: text = fp.read()
	#---write a title
	stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
	header_text = ("# %s\n"%plotname+"\n*an OMNICALC plot script*\n\nGenerated on `%s`. "+
		"Visit the [notebook server](/tree/calc/%s/calcs/) for other calculations.")%(stamp,settings.NAME)
	nb['cells'].append(nbf.v4.new_markdown_cell(header_text))
	#---write the header cell
	nb['cells'].append(nbf.v4.new_code_cell(header_code.strip()%
		shared_work.plot_scripts[plotname]['plotname']))
	#---expose ipython commands hidden in the text
	text_exposed = re.sub('# live:\s+','',text)
	text_exposed_shell = re.sub('# live shell:','!',text_exposed)
	#---write the remaining blocks with double-newlines demiting the cells
	text_no_hashbang = re.match(regex_hashbang,text_exposed_shell,flags=re.M+re.DOTALL).group(1)
	#---split keeps the delimiters and we associate them with the trailing chunks
	chunks = re.split(regex_splitter,text_no_hashbang)
	chunks = [chunks[0]]+[chunks[i]+chunks[i+1] for i in range(1,len(chunks),2)]
	for chunk in chunks:
		nb['cells'].append(nbf.v4.new_code_cell(re.sub('\t',' '*tab_width,chunk.strip())))
	#---check if this is an autoplot
	#---! disabled the following extras until we formalize the style guide for interactive scripts
	if False and shared_work.plot_scripts[plotname]['autoplot']:
		nb['cells'].append(nbf.v4.new_code_cell(
			r"status('this plot script uses the autoplot scheme',tag='note')"+
			'\n'+'plotrun.loader() # run the loader function'+'\n'+
			r"status('you must choose to execute one of the available "+
				r"plots: %s'%"+'\n'+r"', '.join('%s()'%i for i in plotrun.plot_functions),tag='note')"+'\n'
			r"status('the user must run the plots in a new cell',tag='note')"))
	#---write the notebook
	with open(os.path.join(cwd,dest),'w') as fp: nbf.write(nb,fp)

def view_redirector(request):
	"""
	Redirect to the index while retaining the workspace and pictures flags.
	This helps ensure that going to "workspace only" hides the pictures when you do other things.
	"""
	return HttpResponseRedirect(reverse('calculator:index',
		kwargs={'workspace':request.GET.get('workspace','true'),
		'pictures':request.GET.get('pictures','true')}))

def compute(request,meta_fns=None,debug=None):
	"""Run a compute request and redirect."""
	global shared_backrun
	#---selecting meta files triggers manipulation of the meta_filter before running the compute
	meta_filter_now = None
	if meta_fns:
		#---read the config to save the meta_filter for later
		config_now = {}
		exec(open(os.path.join(settings.CALC,'config.py')).read(),config_now)
		meta_filter_now = config_now.get('meta_filter',[])
		bash('make unset meta_filter',cwd=settings.CALC,catch=True)
		bash('make set meta_filter %s'%' '.join(meta_fns),cwd=settings.CALC,catch=True)
	#---dev purposes only: in case you go right to compute
	if not shared_backrun: shared_backrun = FactoryBackrun()
	cmd = 'make compute'
	#---use the backrun instance to run make compute. note that this protects against simultaneous runs
	print('[STATUS] running `%s`'%cmd)
	#---! old method is just one command: shared_backrun.run(cmd=cmd,log='log-compute')
	shared_backrun.run(cmd='\n'.join(['make compute']+
		([]#['make set meta_filter %s'%(' '.join(meta_filter_now))] 
			if meta_filter_now else [])),log='log-compute',use_bash=True)
	return view_redirector(request)

def logging(request):
	"""Serve logging requests from AJAX to the console."""
	global shared_backrun
	logstate = shared_backrun.logstate()
	if logstate: return JsonResponse(logstate)
	else: HttpResponseRedirect(reverse('calculator:index'))

def logging_false(request):
	"""
	Report on a running simulation if one exists.
	Note that getting teh status of the simulation automatically provides the filename for the running
	job's log file. Hence we send the log file as a signal to monitor things, then send it back through
	the URL so that the sim_console function (me) needs only to pipe it back to the page. This is 
	way more elegant than using this function to request the file, since we already have it in the detail
	function.
	"""
	global logging_lock,logging_state,logging_text
	#---if the lock file exists and the logging_lock is set then we update the AJAX console
	if logging_state in 'running' and os.path.isfile(logging_lock):
		#---read the log and return
		with open(logging_fn) as fp: logging_text = fp.read()
		return JsonResponse({'line':logging_text,'running':True})
	elif logging_state in 'running' and not os.path.isfile(logging_lock):
		#---return the final json response and turn off the logging_lock so the AJAX calls stop
		logging_lock = False
		logging_state = 'completed'
		#---read the log and return
		with open(logging_fn) as fp: logging_text = fp.read()
		return JsonResponse({'line':logging_text,'running':False})
	elif logging_state in 'idle': 
		return HttpResponseRedirect(reverse('calculator:index'))
		return JsonResponse({'line':'computer is idle','running':True})
	else: return JsonResponse({'line':'logging_state %s'%logging_state,'running':True})

def clear_logging(request):
	"""Turn off logging and hide the console."""
	global shared_backrun
	shared_backrun.state = 'idle'
	return view_redirector(request)

def make_yaml_file(request):
	"""
	Automatically generate a meta file for the simulation times you have.
	Note that this is somewhat experimental. If your master clock is not contiguous then this will not work.
	"""
	#---skip is set for 2ps since we easily get 200ps in a five-minute villin demo
	skip = 2
	master_autogen_meta_fn = 'meta.current.yaml'
	proc = subprocess.Popen('make look times write_json=True',
		cwd=settings.CALC,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	out,error = proc.communicate()
	times = json.loads(re.search('^time_table = (.*?)$',out,flags=re.M).group(1))
	times_avail = {}
	for sn,details in times:
		flat_times = [v2 for k,v in details for k2,v2 in v]
		start_all = int(min([i['start'] for i in flat_times]))
		stop_all = int(max([i['stop'] for i in flat_times]))
		times_avail[sn] = {'start':start_all,'stop':stop_all}
		#except: pass
	#---! hard-coding protein for the automatic generation
	groups = {'protein':'protein'}
	#---turn available times into an obvious slice
	slices = dict()
	for sn,details in times_avail.items():
		slices[str(sn)] = {'groups':dict(groups),'slices':{'current':{'pbc':'mol','groups':['protein'],
			'start':details['start'],'end':details['stop'],'skip':skip}}}
	#---formulate a coherent meta file from the slices
	new_meta = {'slices':slices}
	#---! add protein RMSD here to force creation of slices
	#---! ...note that we may wish to make slices anyway
	new_meta['collections'] = {'all':tuple(slices.keys())}
	new_meta['calculations'] = {'protein_rmsd':{'uptype':'simulation',
		'slice_name':'current','group':'protein','collections':('all')}}
	#---no need to add plots because they are all autodetected and default to calculations in the metadata
	if not os.path.exists(os.path.join(settings.CALC,'calcs','specs')):
		os.makedirs(os.path.join(settings.CALC,'calcs','specs'))
	with open(os.path.join(settings.CALC,'calcs','specs',master_autogen_meta_fn),'w') as fp:
		fp.write(yaml.safe_dump(new_meta,default_flow_style=False))
	return view_redirector(request)	

def make_look_times(request):
	"""
	Make a notebook that lets users check the simulation times.
	"""
	global notebook_token
	#---all tabs are converted to spaces because Jupyter
	tab_width = 4
	out_fn = os.path.join(settings.CALC,'calcs','look-times.ipynb')
	#---basic code for the notebook
	lines = ["cwd = '%s'"%os.path.join(settings.CALC),
		'import os,sys,subprocess,re,json',
		"proc = subprocess.Popen('make look times write_json=True',"+'\n'+
			"cwd=cwd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)",
		'out,error = proc.communicate()',
		"times = json.loads(re.search('^time_table = (.*?)$',out,flags=re.M).group(1))",
		"sys.path.insert(0,os.path.abspath('../omni'))",
		'from datapack import asciitree',
		'for sn,details in times:',
		'\tfor stepname,step in details:',
        '\t\tfor partname,part in step:',
		"\t\t\tprint(''.join([sn.ljust(20,'.'),partname.ljust(20,'.'),",
		"\t\t\t\tstr(part['start']).ljust(10,'.'),str(part['stop']).rjust(10,'.')]))",]
	#---make a new notebook
	nb = nbf.v4.new_notebook()
	#---write a title
	stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
	header_text = ("# INSPECT TRAJECTORY TIMES\n"+"\nan *omnicalc* utility\n\nGenerated on `%s`. "+
		"Visit the [notebook server](/tree/calc/%s/calcs/) for other scripts.")%(stamp,settings.NAME)
	nb['cells'].append(nbf.v4.new_markdown_cell(header_text))
	chunks = ['\n'.join(lines)]
	for chunk in chunks:
		nb['cells'].append(nbf.v4.new_code_cell(re.sub('\t',' '*tab_width,chunk.strip())))
	#---write the notebook
	with open(out_fn,'w') as fp: nbf.write(nb,fp)
	return redirect("http://%s:%s/tree/%s/calcs/look-times.ipynb?token=%s"%(
		settings.NOTEBOOK_IP,settings.NOTEBOOK_PORT,'calc/%s'%settings.NAME,notebook_token))
