#!/usr/bin/env python3
"""Test script for the new encryption implementation with per-encryption salt."""

import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from terrakit.core.security import CredentialEncryption, encrypt_credentials, decrypt_credentials

def test_encryption():
    """Test the new encryption implementation."""
    print("Testing new encryption implementation with per-encryption salt...")
    
    # Test data
    test_credentials = {
        "username": "test_user",
        "password": "secret_password_123",
        "api_key": "sk-1234567890abcdef",
        "database_url": "postgresql://user:pass@localhost:5432/db"
    }
    
    # 1. Test basic encryption/decryption
    print("\n1. Testing basic encryption/decryption...")
    try:
        encrypted = encrypt_credentials(test_credentials)
        print(f"Encrypted data length: {len(encrypted)} characters")
        print(f"Encrypted data (first 50 chars): {encrypted[:50]}...")
        
        decrypted = decrypt_credentials(encrypted)
        print(f"Decrypted successfully: {decrypted == test_credentials}")
        
        if decrypted != test_credentials:
            print("ERROR: Decrypted data doesn't match original!")
            return False
            
    except Exception as e:
        print(f"ERROR in basic test: {e}")
        return False
    
    # 2. Test salt uniqueness
    print("\n2. Testing salt uniqueness...")
    try:
        encrypted1 = encrypt_credentials(test_credentials)
        encrypted2 = encrypt_credentials(test_credentials)
        encrypted3 = encrypt_credentials(test_credentials)
        
        # Each encryption should produce different ciphertext due to unique salts
        if encrypted1 == encrypted2 or encrypted1 == encrypted3 or encrypted2 == encrypted3:
            print("ERROR: Encrypted data is identical (salts not unique)")
            return False
        else:
            print("SUCCESS: Each encryption produces different ciphertext (unique salts)")
        
        # But all should decrypt to the same original data
        decrypted1 = decrypt_credentials(encrypted1)
        decrypted2 = decrypt_credentials(encrypted2)
        decrypted3 = decrypt_credentials(encrypted3)
        
        if decrypted1 == decrypted2 == decrypted3 == test_credentials:
            print("SUCCESS: All encrypted versions decrypt to the same original data")
        else:
            print("ERROR: Decrypted data is inconsistent")
            return False
            
    except Exception as e:
        print(f"ERROR in salt uniqueness test: {e}")
        return False
    
    # 3. Test with different encryption instances
    print("\n3. Testing with different encryption instances...")
    try:
        enc1 = CredentialEncryption()
        enc2 = CredentialEncryption()
        
        encrypted_by_enc1 = enc1.encrypt_credentials(test_credentials)
        decrypted_by_enc2 = enc2.decrypt_credentials(encrypted_by_enc1)
        
        if decrypted_by_enc2 == test_credentials:
            print("SUCCESS: Cross-instance encryption/decryption works")
        else:
            print("ERROR: Cross-instance decryption failed")
            return False
            
    except Exception as e:
        print(f"ERROR in cross-instance test: {e}")
        return False
    
    # 4. Test edge cases
    print("\n4. Testing edge cases...")
    try:
        # Empty credentials
        empty_creds = {}
        encrypted_empty = encrypt_credentials(empty_creds)
        decrypted_empty = decrypt_credentials(encrypted_empty)
        if decrypted_empty != empty_creds:
            print("ERROR: Empty credentials test failed")
            return False
        
        # Large credentials
        large_creds = {"data": "x" * 10000}
        encrypted_large = encrypt_credentials(large_creds)
        decrypted_large = decrypt_credentials(encrypted_large)
        if decrypted_large != large_creds:
            print("ERROR: Large credentials test failed")
            return False
            
        print("SUCCESS: Edge cases passed")
        
    except Exception as e:
        print(f"ERROR in edge cases test: {e}")
        return False
    
    # 5. Test invalid data handling
    print("\n5. Testing invalid data handling...")
    try:
        # Test with invalid base64
        try:
            decrypt_credentials("invalid_base64_data")
            print("ERROR: Should have failed with invalid base64")
            return False
        except:
            print("SUCCESS: Properly handles invalid base64")
        
        # Test with truncated data (less than 16 bytes for salt)
        try:
            short_data = base64.b64encode(b"short").decode()
            decrypt_credentials(short_data)
            print("ERROR: Should have failed with truncated data")
            return False
        except:
            print("SUCCESS: Properly handles truncated data")
            
    except Exception as e:
        print(f"ERROR in invalid data test: {e}")
        return False
    
    print("\n✅ All tests passed! New encryption implementation is working correctly.")
    return True

if __name__ == "__main__":
    import base64
    success = test_encryption()
    sys.exit(0 if success else 1)