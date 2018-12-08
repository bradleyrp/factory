from django.conf import settings

def global_settings(request):
	"""
	Export key variables to the HTML templates.
	"""
	return {
		'NOTEBOOK_PORT':settings.NOTEBOOK_PORT,
		'NOTEBOOK_IP':settings.NOTEBOOK_IP,
		'NAME':settings.NAME}