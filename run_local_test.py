"""Run this on the host/workspace to test importing and basic endpoints.

Usage (Windows PowerShell with configured venv):
//192.168.10.163/docker/approval_mvp/.venv/Scripts/python.exe run_local_test.py

Or, inside venv activate then:
python run_local_test.py
"""
import os, sys, traceback
from pathlib import Path

# configure env to avoid using production data dir
ROOT = Path(__file__).resolve().parent
os.environ.setdefault('APP_DATA_DIR', str(ROOT / 'data_test'))
os.environ.setdefault('APP_SECRET','testsecret')
os.environ.setdefault('APP_ADMIN_ID','admin')
os.environ.setdefault('APP_ADMIN_PW','admin1234!')

# ensure repo root on path
sys.path.insert(0, str(ROOT))

print('Working dir:', ROOT)
print('PYTHONPATH includes:', sys.path[0])

try:
    import importlib
    main = importlib.import_module('app.main')
    print('Imported app.main OK')
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get('/login')
    print('GET /login ->', r.status_code)
    r_root = client.get('/')
    print('GET / ->', r_root.status_code, 'location->', r_root.headers.get('location'))
    # Try a protected endpoint to ensure dependency wiring (expected 401)
    r_doc = client.get('/doc/test-create')
    print('GET /doc/test-create ->', r_doc.status_code)
except Exception:
    print('Exception during test run:')
    traceback.print_exc()
