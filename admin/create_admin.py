import os
import logging
import bcrypt
from dotenv import load_dotenv
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.database import User, Session

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


username = os.getenv("ADMIN_USERNAME")
password = os.getenv("ADMIN_PASSWORD")
if not username or not password:
    logger.error("ADMIN_USERNAME and ADMIN_PASSWORD must be set in the .env file")
    raise ValueError("ADMIN_USERNAME and ADMIN_PASSWORD must be set in the .env file")

def create_admin_user():
    """Create an admin user in the database if it doesn't exist."""
    session = Session()
    try:
        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            logger.info(f"User '{username}' already exists in the database.")
            return
        
        # Create new admin user
        hashed_password = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")
        
        new_user = User(
            username=username,
            password=hashed_password,
            is_admin=True
        )
        
        session.add(new_user)
        session.commit()
        logger.info(f"Admin user '{username}' created successfully.")
        
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    try:
        create_admin_user()
    except Exception as e:
        logger.error(f"Failed to initialize admin user: {str(e)}")
        sys.exit(1)