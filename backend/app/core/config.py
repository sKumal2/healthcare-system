# app/core/config.py
from pydantic_settings import BaseSettings  # or from pydantic_settings import BaseSettings in newer templates
from pydantic import AnyHttpUrl   # optional but nice
from typing import List, Union

class Settings(BaseSettings):
    BACKEND_CORS_ORIGINS: Union[List[AnyHttpUrl], str] = []   # ← add this annotation
    # or more commonly:
    # BACKEND_CORS_ORIGINS: List[str] = []

    # other settings...