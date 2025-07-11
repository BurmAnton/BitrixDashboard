"""
WSGI config for bitrix24_integration project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bitrix24_integration.settings')

application = get_wsgi_application() 