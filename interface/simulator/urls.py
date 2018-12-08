from django.conf.urls import url

from . import views
from . import interact

app_name = 'simulator'

urlpatterns = [
	url(r'^$',views.index,name='index'),
	url(r'^builder$',views.index,name='builder'),
	url(r'^sim(?P<id>[0-9]+)/?$',views.detail_simulation,name='detail_simulation'),
	url(r'^upload_coordinates$',views.upload_coordinates,name='upload_coordinates'),
	url(r'^sim(?P<id_sim>[0-9]+)/kick(?P<id_kick>[0-9]+)$',interact.make_setup,name='make_setup'),
	url(r'^sim(?P<id_sim>[0-9]+)/prep/(?P<expt_name>\w+)$',interact.make_prep,name='make_prep'),
	url(r'^cluster_view',views.cluster_view,name='cluster_view'),
	url(r'^sim_console/(?P<log_fn>.*?)$',views.sim_console,name='sim_console'),
]