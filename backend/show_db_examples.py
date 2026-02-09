from sqlmodel import Session, select
from app.database import engine
from app.models import Movie
import json
import sys

with Session(engine) as session:
    # 示例 1: 已完成分析的电影
    analyzed = session.exec(select(Movie).where(Movie.analysis_status == 'completed')).first()
    
    print("=" * 80)
    print("示例 1: 已完成分析的电影")
    print("=" * 80)
    if analyzed:
        print(f"\n基本信息:")
        print(f"  ID: {analyzed.id}")
        print(f"  标题: {analyzed.title} ({analyzed.year})")
        print(f"  中文标题: {analyzed.title_cn}")
        print(f"  TMDB ID: {analyzed.tmdb_id}")
        print(f"  导演: {analyzed.director}")
        print(f"  流派: {analyzed.genres}")
        print(f"\n分析结果:")
        print(f"  状态: {analyzed.analysis_status}")
        print(f"  微流派: {analyzed.micro_genre}")
        print(f"  微流派定义: {analyzed.micro_genre_definition}")
        if analyzed.analysis_data:
            print(f"\nanalysis_data 结构:")
            print(json.dumps(analyzed.analysis_data, indent=2, ensure_ascii=False))
    
    # 示例 2: 未分析的 NFO 电影
    pending = session.exec(
        select(Movie)
        .where(Movie.analysis_status == 'pending')
        .where(Movie.nfo_source == 'tmm')
    ).first()
    
    print("\n" + "=" * 80)
    print("示例 2: 待分析的电影 (从 NFO 导入)")
    print("=" * 80)
    if pending:
        print(f"\n基本信息:")
        print(f"  ID: {pending.id}")
        print(f"  标题: {pending.title} ({pending.year})")
        print(f"  中文标题: {pending.title_cn}")
        print(f"  TMDB ID: {pending.tmdb_id}")
        print(f"  导演: {pending.director}")
        print(f"  本地海报: {pending.poster_local}")
        print(f"  NFO 来源: {pending.nfo_source}")
        print(f"\n分析结果:")
        print(f"  状态: {pending.analysis_status}")
        print(f"  微流派: {pending.micro_genre}")
        print(f"  analysis_data: {pending.analysis_data}")
