import random
import sys
from app.db import SessionLocal, init_db, School

init_db()
mode = (sys.argv[1] if len(sys.argv) > 1 else '').lower()

with SessionLocal() as db:
    schools = db.query(School).all()
    if mode == 'demo':
        for school in schools:
            school.artificial_clicks += random.randint(100, 2300)
        db.commit()
        print(f'Added demo activity to {len(schools)} schools.')
    elif mode == 'clear-demo':
        for school in schools:
            school.artificial_clicks = 0
        db.commit()
        print('Artificial activity cleared.')
    else:
        print('Usage: python seed.py demo | clear-demo')
