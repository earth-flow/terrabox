#!/usr/bin/env python3
"""添加example工具包到数据库"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from terralink_platform.db.session import get_db
from terralink_platform.db.models import Toolkit
from terralink_platform.core.utils.config import settings

def add_example_toolkit():
    """添加example工具包到数据库"""
    db = next(get_db())
    
    try:
        # 检查是否已存在
        existing = db.query(Toolkit).filter(Toolkit.key == "example").first()
        if existing:
            print(f"Example工具包已存在: {existing.key} - {existing.name}")
            return
        
        # 创建新的工具包记录
        example_toolkit = Toolkit(
            id=2,  # 手动设置ID，因为GitHub工具包是1
            key="example",
            name="Example Toolkit",
            description="Example toolkit demonstrating the plugin system",
            toolkit_type="mcp",
            is_active=True
        )
        
        db.add(example_toolkit)
        db.commit()
        
        print(f"✅ 成功添加example工具包到数据库")
        print(f"  - Key: {example_toolkit.key}")
        print(f"  - Name: {example_toolkit.name}")
        print(f"  - Description: {example_toolkit.description}")
        print(f"  - Active: {example_toolkit.is_active}")
        
    except Exception as e:
        print(f"❌ 添加example工具包失败: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_example_toolkit()