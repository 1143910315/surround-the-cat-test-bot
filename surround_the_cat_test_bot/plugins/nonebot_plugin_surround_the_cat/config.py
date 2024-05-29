from pydantic import BaseModel
import os

class Config(BaseModel):
    """Plugin Config Here"""
    # 缓存图片目录，默认为 'cache'
    imageCacheDirectory: str = os.getenv('IMAGE_CACHE_DIRECTORY', 'cache')
    # 缓存图片数量，默认为 30
    imageCacheCount: int = int(os.getenv('IMAGE_CACHE_COUNT', 30))
    
