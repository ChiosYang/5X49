"""
数据库重建脚本

从 NFO 文件重新扫描并构建数据库。
此脚本用于清空重建整个电影库数据库。

使用方法:
    python scripts/rebuild_db.py [media_dir]

参数:
    media_dir: NFO 文件所在目录（可选，默认使用环境变量 MEDIA_DIR）
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import create_db_and_tables, engine
from app.services.scanner import NFOScanner
from app.models import Movie
from sqlmodel import Session, delete

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("rebuild_db")

def rebuild_database(media_dir: str = None):
    """
    重建数据库：清空现有数据并从 NFO 文件重新扫描。
    
    Args:
        media_dir: NFO 文件所在的媒体目录
    """
    # 使用参数或环境变量
    target_dir = media_dir or os.getenv("MEDIA_DIR")
    
    if not target_dir:
        logger.error("请提供媒体目录路径或设置 MEDIA_DIR 环境变量")
        sys.exit(1)
    
    if not os.path.exists(target_dir):
        logger.error(f"目录不存在: {target_dir}")
        sys.exit(1)
    
    logger.info(f"开始重建数据库，扫描目录: {target_dir}")
    
    # 1. 创建表结构（如果不存在）
    logger.info("创建数据库表...")
    create_db_and_tables()
    
    # 2. 清空现有数据
    logger.info("清空现有电影数据...")
    with Session(engine) as session:
        session.exec(delete(Movie))
        session.commit()
    
    # 3. 扫描 NFO 文件
    logger.info("扫描 NFO 文件...")
    scanner = NFOScanner(target_dir)
    movies = scanner.scan()
    
    if not movies:
        logger.warning("未发现任何 NFO 文件")
        return
    
    # 4. 导入到数据库
    logger.info(f"导入 {len(movies)} 部电影到数据库...")
    count = 0
    with Session(engine) as session:
        for movie_dict in movies:
            try:
                movie = Movie(**movie_dict)
                session.add(movie)
                count += 1
            except Exception as e:
                logger.error(f"导入电影失败 {movie_dict.get('title', 'Unknown')}: {e}")
        
        session.commit()
    
    logger.info(f"✅ 数据库重建完成！成功导入 {count} 部电影")

if __name__ == "__main__":
    media_dir = sys.argv[1] if len(sys.argv) > 1 else None
    rebuild_database(media_dir)
