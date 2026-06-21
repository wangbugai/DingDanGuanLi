import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.app import app, init_db
with app.app_context():
    init_db()
print('DB init done')
