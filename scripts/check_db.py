from sqlalchemy import text
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import SessionLocal, User


if __name__ == '__main__':
    db = SessionLocal()
    try:
        tables = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
        print('tables:', tables)
        admin = None
        try:
            admin = db.query(User).filter(User.username=='admin').first()
            print('admin found:', bool(admin))
            if admin:
                print('admin id', admin.id, 'username', admin.username, 'is_admin', admin.is_admin)
        except Exception as e:
            print('query users failed:', e)
    finally:
        db.close()
