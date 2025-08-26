#!/usr/bin/env python3
"""Update OAuth provider configurations from environment variables."""

import os
import sqlite3
from pathlib import Path
from datetime import datetime

def update_oauth_providers():
    """Update OAuth provider configurations in database."""
    # Get environment variables
    github_client_id = os.getenv('GITHUB_OAUTH_CLIENT_ID')
    github_client_secret = os.getenv('GITHUB_OAUTH_CLIENT_SECRET')
    google_client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
    
    # Database path
    db_path = Path(__file__).parent.parent / "terralink_platform.db"
    
    # Update database
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # GitHub OAuth provider
        if github_client_id and github_client_secret:
            cursor.execute(
                """INSERT OR REPLACE INTO oauth_providers 
                   (name, display_name, client_id, client_secret, auth_url, token_url, user_info_url, scopes, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    'github',
                    'GitHub',
                    github_client_id,
                    github_client_secret,
                    'https://github.com/login/oauth/authorize',
                    'https://github.com/login/oauth/access_token',
                    'https://api.github.com/user',
                    'repo,user:email',
                    True,
                    datetime.utcnow()
                )
            )
            print(f"Updated GitHub OAuth provider with client_id: {github_client_id}")
        else:
            print("Warning: GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET not set")
        
        # Google OAuth provider
        if google_client_id and google_client_secret:
            cursor.execute(
                """INSERT OR REPLACE INTO oauth_providers 
                   (name, display_name, client_id, client_secret, auth_url, token_url, user_info_url, scopes, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    'google',
                    'Google',
                    google_client_id,
                    google_client_secret,
                    'https://accounts.google.com/o/oauth2/auth',
                    'https://oauth2.googleapis.com/token',
                    'https://www.googleapis.com/oauth2/v2/userinfo',
                    'openid,email,profile',
                    True,
                    datetime.utcnow()
                )
            )
            print(f"Updated Google OAuth provider with client_id: {google_client_id}")
        else:
            print("Warning: GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET not set")
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error updating OAuth providers: {e}")
        return False
    
    return True

if __name__ == "__main__":
    update_oauth_providers()