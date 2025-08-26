#!/usr/bin/env python3

import sqlite3
import os

def main():
    # Check actual database schema
    print("=== Actual Database Schema ===")
    db_path = "terralink_platform.db"
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tool_overrides table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool_overrides'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            print("tool_overrides table exists")
            cursor.execute("PRAGMA table_info(tool_overrides)")
            columns = cursor.fetchall()
            print("tool_overrides table structure:")
            for col in columns:
                print(f"  {col[1]}: {col[2]} (pk={col[5]}, not_null={col[3]}, default={col[4]})")
        else:
            print("tool_overrides table does not exist")
            
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"\nAll tables in database: {[t[0] for t in tables]}")
        
        conn.close()
    else:
        print("Database file does not exist")

if __name__ == "__main__":
    main()