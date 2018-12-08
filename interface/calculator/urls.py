from django.conf.urls import url
from django.conf.urls.static import static
from django.conf import settings

from . import views

app_name = 'calculator'

urlpatterns = [
	url(r'^$',views.index,name='index'),
	url(r'^$',views.index,kwargs={'workspace':'true','pictures':'true'},name='index'),
	url(r'^workspace$',views.index,kwargs={'workspace':'true','pictures':'false'},name='index'),
	url(r'^pictures$',views.index,kwargs={'workspace':'false','pictures':'true',
		'show_pictures':True},name='index'),
	url(r'^clear_logging$',views.clear_logging,name='clear_logging'),
	url(r'^refresh$',views.refresh,name='refresh'),
	url(r'^clear_stale$',views.clear_stale,name='refresh'),
	url(r'^refresh_thumbnails$',views.refresh_thumbnails,name='refresh_thumbnails'),
	url(r'^compute$',views.compute,name='compute'),
	url(r'^get_code/(?P<name>.+)$',views.get_code,name='get_code'),
	url(r'^make_notebook/(?P<name>.+)$',views.make_notebook,name='make_notebook'),
	url(r'^make_yaml_file$',views.make_yaml_file,name='make_yaml_file'),
	url(r'^make_look_times$',views.make_look_times,name='make_look_times'),
	url(r'^logging$',views.logging,name='logging'),
]

#---static paths
urlpatterns += static('/media/raw/',document_root=settings.PLOT)
