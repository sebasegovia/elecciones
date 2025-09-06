# wsgi.py
from app import app  # importa el objeto Flask llamado "app" desde app.py

# Gunicorn buscará una variable llamada "app" en este módulo
# por eso NO la renombramos.
