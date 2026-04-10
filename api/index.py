import os
import sys
import shutil
from django.core.wsgi import get_wsgi_application

# Robust path handling
path = os.path.dirname(os.path.dirname(__file__))
if path not in sys.path:
    sys.path.append(path)

# Vercel Serverless Hack for SQLite
if os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_URL'):
    source_db = os.path.join(path, 'db.sqlite3')
    dest_db = '/tmp/db.sqlite3'
    if os.path.exists(source_db) and not os.path.exists(dest_db):
        try:
            shutil.copy2(source_db, dest_db)
        except Exception:
            pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager_django.settings')

app = get_wsgi_application()
