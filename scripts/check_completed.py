import os
import sys
import requests
from itsdangerous import URLSafeSerializer
# ensure project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import APP_SECRET, SessionLocal, User

BASE = os.getenv('APP_URL', 'http://127.0.0.1:8000')

s = requests.Session()
serializer = URLSafeSerializer(APP_SECRET, salt="approval_mvp_session")

# get admin id from DB
db = SessionLocal()
admin = db.query(User).filter(User.username == os.getenv('APP_ADMIN_ID', 'admin')).first()
db.close()
if not admin:
    print('No admin user found')
    raise SystemExit(1)

s.cookies.set('session', serializer.dumps({'uid': admin.id}))

try:
    r = s.get(BASE.rstrip('/') + '/completed', timeout=10)
    print('/completed ->', r.status_code, 'len', len(r.text))
    print('snippet:', r.text[:500])
except Exception as e:
    print('error', e)
