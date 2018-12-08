from bs4 import BeautifulSoup
from django import template
from django.template.defaultfilters import stringfilter
import pygments
import pygments.formatters
from pygments import highlight
from pygments.lexers import PythonLexer

register = template.Library()

@register.filter
@stringfilter
def highlight(code):

	"""
	Python syntax highlighting.
	Make a new pygments CSS file with the following commands.
	python -c "style='pastie';import sys;from pygments.formatters import HtmlFormatter;
	f=open(sys.argv[1], 'w');f.write(HtmlFormatter(style=style).get_style_defs('.highlight'));
	f.close()" dev/calculator/static/calculator/pygments.css
	"""
	
	formatter = pygments.formatters.HtmlFormatter(linenos='table')
	return pygments.highlight(code,PythonLexer(tabsize=4),formatter)
