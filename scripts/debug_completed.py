import os
import sys
import traceback
# ensure project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import app, APP_SECRET, SessionLocal, User
from itsdangerous import URLSafeSerializer
from fastapi.testclient import TestClient

client = TestClient(app)
serializer = URLSafeSerializer(APP_SECRET, salt="approval_mvp_session")

db = SessionLocal()
admin = db.query(User).filter(User.username == os.getenv('APP_ADMIN_ID', 'admin')).first()
db.close()
if not admin:
    print('No admin user')
    raise SystemExit(1)

client.cookies.set('session', serializer.dumps({'uid': admin.id}))

try:
    r = client.get('/completed')
    print('/completed ->', r.status_code)
    print('len', len(r.text))
    print(r.text[:1000])
except Exception as e:
    print('exception during request:')
    traceback.print_exc()
