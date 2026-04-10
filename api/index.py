import os
import sys
import shutil
from django.core.wsgi import get_wsgi_application  # type: ignore

# Robust path handling
path = os.path.dirname(os.path.dirname(__file__))
if path not in sys.path:
    sys.path.append(path)



os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager_django.settings')

app = get_wsgi_application()
