import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

    # MySQL Bangalore
    MYSQL_BANGALORE_HOST: str = os.getenv("MYSQL_BANGALORE_HOST", "localhost")
    MYSQL_BANGALORE_PORT: int = int(os.getenv("MYSQL_BANGALORE_PORT", "3306"))
    MYSQL_BANGALORE_USER: str = os.getenv("MYSQL_BANGALORE_USER", "ev_user")
    MYSQL_BANGALORE_PASSWORD: str = os.getenv("MYSQL_BANGALORE_PASSWORD", "evcharge_pass_2024")
    MYSQL_BANGALORE_DB: str = os.getenv("MYSQL_BANGALORE_DB", "ev_bangalore")

    # MySQL Chennai
    MYSQL_CHENNAI_HOST: str = os.getenv("MYSQL_CHENNAI_HOST", "localhost")
    MYSQL_CHENNAI_PORT: int = int(os.getenv("MYSQL_CHENNAI_PORT", "3307"))
    MYSQL_CHENNAI_USER: str = os.getenv("MYSQL_CHENNAI_USER", "ev_user")
    MYSQL_CHENNAI_PASSWORD: str = os.getenv("MYSQL_CHENNAI_PASSWORD", "evcharge_pass_2024")
    MYSQL_CHENNAI_DB: str = os.getenv("MYSQL_CHENNAI_DB", "ev_chennai")

    # MySQL Delhi
    MYSQL_DELHI_HOST: str = os.getenv("MYSQL_DELHI_HOST", "localhost")
    MYSQL_DELHI_PORT: int = int(os.getenv("MYSQL_DELHI_PORT", "3308"))
    MYSQL_DELHI_USER: str = os.getenv("MYSQL_DELHI_USER", "ev_user")
    MYSQL_DELHI_PASSWORD: str = os.getenv("MYSQL_DELHI_PASSWORD", "evcharge_pass_2024")
    MYSQL_DELHI_DB: str = os.getenv("MYSQL_DELHI_DB", "ev_delhi")

    # MongoDB
    MONGODB_HOST: str = os.getenv("MONGODB_HOST", "localhost")
    MONGODB_PORT: int = int(os.getenv("MONGODB_PORT", "27017"))
    MONGODB_USER: str = os.getenv("MONGODB_USER", "ev_admin")
    MONGODB_PASSWORD: str = os.getenv("MONGODB_PASSWORD", "evcharge_mongo_2024")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "ev_realtime")

    @property
    def mysql_bangalore_url(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_BANGALORE_USER}:{self.MYSQL_BANGALORE_PASSWORD}@{self.MYSQL_BANGALORE_HOST}:{self.MYSQL_BANGALORE_PORT}/{self.MYSQL_BANGALORE_DB}"

    @property
    def mysql_chennai_url(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_CHENNAI_USER}:{self.MYSQL_CHENNAI_PASSWORD}@{self.MYSQL_CHENNAI_HOST}:{self.MYSQL_CHENNAI_PORT}/{self.MYSQL_CHENNAI_DB}"

    @property
    def mysql_delhi_url(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_DELHI_USER}:{self.MYSQL_DELHI_PASSWORD}@{self.MYSQL_DELHI_HOST}:{self.MYSQL_DELHI_PORT}/{self.MYSQL_DELHI_DB}"

    @property
    def mongodb_url(self) -> str:
        return f"mongodb://{self.MONGODB_USER}:{self.MONGODB_PASSWORD}@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DB}?authSource=admin"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
