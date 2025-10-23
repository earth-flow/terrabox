#!/usr/bin/env python3
"""Database initialization and test data creation script."""

import sys
import os
from pathlib import Path

# Add src to path so we can import our modules
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from terrakit.core.utils.config import settings
from terrakit.db.models import Base, User, ApiKey
from terrakit.core.utils.auth import hash_password, generate_api_key, hash_api_key, generate_public_id
from datetime import datetime


def create_database_if_not_exists():
    """Create database if it doesn't exist (for PostgreSQL)."""
    if "postgresql" in settings.DB_URL:
        # Extract database name from URL
        db_name = settings.DB_URL.split("/")[-1]
        base_url = settings.DB_URL.rsplit("/", 1)[0]
        
        # Connect to postgres database to create our database
        engine = create_engine(f"{base_url}/postgres")
        
        with engine.connect() as conn:
            # Check if database exists
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                {"db_name": db_name}
            )
            
            if not result.fetchone():
                # Create database
                conn.execute(text("COMMIT"))  # End any transaction
                conn.execute(text(f"CREATE DATABASE {db_name}"))
                print(f"Created database: {db_name}")
            else:
                print(f"Database {db_name} already exists")


def init_database():
    """Initialize database tables."""
    print(f"Initializing database with URL: {settings.DB_URL}")
    
    # Create database if needed
    create_database_if_not_exists()
    
    # Create engine and tables
    engine = create_engine(settings.DB_URL)
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")
    
    return engine


def create_test_data(engine):
    """Create test data for development and testing."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Create test users
        test_users = [
            {
                "user_id": "testuser1",
                "email": "test1@example.com",
                "password": "password123"
            },
            {
                "user_id": "testuser2",
                "email": "test2@example.com",
                "password": "password123"
            },
            {
                "user_id": "admin",
                "email": "admin@example.com",
                "password": "admin123"
            }
        ]
        
        created_users = []
        for user_data in test_users:
            # Check if user already exists
            existing_user = db.query(User).filter(
                (User.email == user_data["email"]) | (User.user_id == user_data["user_id"])
            ).first()
            
            if existing_user:
                print(f"User {user_data['user_id']} already exists, skipping")
                created_users.append(existing_user)
                continue
            
            # Create new user
            user = User(
                user_id=user_data["user_id"],
                email=user_data["email"],
                password_hash=hash_password(user_data["password"]),
                is_active=True
            )
            
            db.add(user)
            db.commit()
            db.refresh(user)
            
            created_users.append(user)
            print(f"Created user: {user.user_id} ({user.email})")
        
        # Create API keys for test users
        for user in created_users:
            # Check if user already has API keys
            existing_keys = db.query(ApiKey).filter(ApiKey.user_id_fk == user.id).count()
            if existing_keys > 0:
                print(f"User {user.user_id} already has API keys, skipping")
                continue
            
            # Create a test API key
            api_key = generate_api_key()
            public_id = generate_public_id()
            hashed_key = hash_api_key(api_key)
            
            db_api_key = ApiKey(
                user_id_fk=user.id,
                label="Test API Key",
                public_id=public_id,
                secret_hash=hashed_key,
                is_active=True
            )
            
            db.add(db_api_key)
            db.commit()
            
            print(f"Created API key for {user.user_id}: {api_key}")
        
        print("\n=== Test Data Summary ===")
        print("Users created:")
        for user in created_users:
            print(f"  - {user.user_id} ({user.email})")
        
        print("\nAPI Keys created:")
        for user in created_users:
            api_keys = db.query(ApiKey).filter(
                ApiKey.user_id_fk == user.id,
                ApiKey.is_active == True
            ).all()
            
            for api_key in api_keys:
                print(f"  - {user.user_id}: {api_key.public_id}")
        
    except Exception as e:
        print(f"Error creating test data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """Main function to initialize database and create test data."""
    print("Starting database initialization...")
    
    try:
        # Initialize database
        engine = init_database()
        
        # Create test data
        print("\nCreating test data...")
        create_test_data(engine)
        
        print("\nDatabase initialization completed successfully!")
        print("\nYou can now:")
        print("1. Start the server: uvicorn terrakit.main:app --reload")
        print("2. Test user registration and login with the created test users")
        print("3. Use the API keys for SDK testing")
        
    except Exception as e:
        print(f"Error during initialization: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()