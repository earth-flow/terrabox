#!/usr/bin/env python3
"""Initialize test OAuth providers for development."""

import sys
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from terralink_platform.db.session import get_db
from terralink_platform.db import models as m
from datetime import datetime

def init_test_oauth_providers():
    """Initialize test OAuth providers for development."""
    db = next(get_db())
    
    try:
        # Check if providers already exist
        existing_providers = db.query(m.OAuthProvider).count()
        if existing_providers > 0:
            print(f"Found {existing_providers} existing OAuth providers, skipping initialization.")
            return
        
        # Create test GitHub OAuth provider
        github_provider = m.OAuthProvider(
            name='github',
            display_name='GitHub',
            client_id='Ov23liRzD7AXQH0y5fFo',
            client_secret='b49440bcbd4c252f5f0c0a7d2f290b0c272dc5c5',
            auth_url='https://github.com/login/oauth/authorize',
            token_url='https://github.com/login/oauth/access_token',
            user_info_url='https://api.github.com/user',
            scopes='repo,user:email',
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        # Create test Google OAuth provider
        google_provider = m.OAuthProvider(
            name='google',
            display_name='Google',
            client_id='116921976899-s0ikr354ecjm77r8ma20bdprtrbgiged.apps.googleusercontent.com',
            client_secret='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',
            auth_url='https://accounts.google.com/o/oauth2/auth',
            token_url='https://oauth2.googleapis.com/token',
            user_info_url='https://www.googleapis.com/oauth2/v2/userinfo',
            scopes='openid email profile',
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(github_provider)
        db.add(google_provider)
        db.commit()
        
        print("Successfully initialized test OAuth providers:")
        print("- GitHub (test_github_client_id)")
        print("- Google (test_google_client_id)")
        print("\nNote: These are test providers for development only.")
        print("For production, set proper GITHUB_OAUTH_CLIENT_ID, GITHUB_OAUTH_CLIENT_SECRET,")
        print("GOOGLE_OAUTH_CLIENT_ID, and GOOGLE_OAUTH_CLIENT_SECRET environment variables.")
        
    except Exception as e:
        print(f"Error initializing OAuth providers: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_test_oauth_providers()