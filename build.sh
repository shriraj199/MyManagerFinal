#!/bin/bash

echo "Building the project..."

# Use python3 generically
export PATH=$PATH:/usr/local/bin

pip install urllib3==1.26.15 requests-toolbelt==0.10.1
pip install -r requirements.txt

echo "Run Database Migrations..."
python manage.py migrate

echo "Collect Static..."
python manage.py collectstatic --noinput --clear

echo "Build complete."
