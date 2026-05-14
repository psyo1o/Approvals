import os
import sys
import requests
from itsdangerous import URLSafeSerializer

# ensure project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import DB_PATH, APP_SECRET
from app.main import SessionLocal, User

BASE = os.getenv('APP_URL', 'http://localhost:8000')

s = requests.Session()

# create session cookie for admin
serializer = URLSafeSerializer(APP_SECRET, salt="approval_mvp_session")

db = SessionLocal()
admin = db.query(User).filter(User.username == os.getenv('APP_ADMIN_ID', 'admin')).first()
db.close()
if not admin:
    print('No admin user found, abort')
    sys.exit(1)

cookie_val = serializer.dumps({"uid": admin.id})
# set cookie without domain so it applies to the requested host
s.cookies.set('session', cookie_val)

pages = ["/", "/login", "/dashboard", "/org", "/calendar", "/boards"]

for p in pages:
    url = BASE.rstrip('/') + p
    try:
        r = s.get(url, timeout=5)
        print(url, '->', r.status_code, 'len', len(r.text))
        if r.status_code == 200:
            if '사내 조직도' in r.text:
                print('  contains org marker')
            if '사내 일정 관리' in r.text:
                print('  contains calendar marker')
    except Exception as e:
        print(url, 'error', e)

# test events API
try:
    r = s.get(BASE.rstrip('/') + '/api/events')
    print('/api/events ->', r.status_code, r.headers.get('content-type'))
    print('json len', len(r.json()))
except Exception as e:
    print('/api/events error', e)
