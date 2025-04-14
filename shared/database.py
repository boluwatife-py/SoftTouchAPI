from sqlalchemy import create_engine, Column, String, Boolean, Integer, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
import sqlite3

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///api.db')
engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)  # Hashed with bcrypt
    is_admin = Column(Boolean, default=False)

class ApiEndpoint(Base):
    __tablename__ = 'api_endpoints'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    method = Column(String, nullable=False)
    endpoint = Column(String, nullable=False, unique=True)
    response_type = Column(String, nullable=False)
    part_description = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    params = Column(Text, nullable=False)  # JSON string of params
    sample_request = Column(Text, nullable=True)  # JSON string of sample request
    sample_response = Column(Text, nullable=True)  # JSON string of sample response
    enabled = Column(Boolean, default=True)
    is_visible_in_stats = Column(Boolean, default=True)

class ApiStat(Base):
    __tablename__ = 'api_stats'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    daily_requests = Column(Integer, default=0)
    weekly_requests = Column(Integer, default=0)
    monthly_requests = Column(Integer, default=0)
    average_response_time = Column(Float, default=0.0)
    success_rate = Column(Float, default=0.0)
    popularity = Column(Float, default=0.0)
    last_updated = Column(DateTime)

class Statistic(Base):
    __tablename__ = 'statistics'
    id = Column(Integer, primary_key=True)
    total_requests = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    timestamp = Column(DateTime, default=None)

class RequestLog(Base):
    __tablename__ = 'request_log'
    id = Column(Integer, primary_key=True)
    api_name = Column(String)
    client_ip = Column(String)
    response_time = Column(Float)
    status_code = Column(Integer)
    timestamp = Column(DateTime)

# Create tables
Base.metadata.create_all(engine)

# Session factory
Session = sessionmaker(bind=engine)

# SQLite connection for app.py compatibility
def get_db():
    conn = sqlite3.connect('api.db')
    conn.row_factory = sqlite3.Row
    return conn