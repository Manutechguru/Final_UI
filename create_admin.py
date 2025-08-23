from landing_page_app.database import SessionLocal
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from passlib.hash import bcrypt

db = SessionLocal()

email = "admin@example.com"
password = "admin123"

# Check if admin exists
admin = db.query(User).filter(User.email == email).first()
if not admin:
    admin = User(
        full_name="Admin",
        email=email,
        hashed_password=bcrypt.hash(password),
        role=UserRole.ADMIN,
        is_active=True
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    log = UserLog(user_id=admin.id, action="ADMIN CREATED")
    db.add(log)
    db.commit()
    print("✅ Admin user created")
else:
    print("⚠️ Admin already exists:", admin.email)
