import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.app import app
app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
