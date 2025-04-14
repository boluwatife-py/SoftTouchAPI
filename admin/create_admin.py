import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bcrypt
from dotenv import load_dotenv
from shared.database import User, Session

# Load environment variables
load_dotenv()
username = os.getenv("ADMIN_USERNAME")
password = os.getenv("ADMIN_PASSWORD")

if not username or not password:
    raise ValueError("ADMIN_USERNAME and ADMIN_PASSWORD must be set in the .env file")

# Start DB session
session = Session()

# Check if user exists
existing_user = session.query(User).filter_by(username=username).first()
if existing_user:
    print(f"User '{username}' already exists.")
else:
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    new_user = User(username=username, password=hashed_password, is_admin=True)
    session.add(new_user)
    session.commit()
    print(f"Admin user '{username}' created successfully.")

session.close()
