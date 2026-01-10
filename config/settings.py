"""
Configuration module for Metin2 Data Warehouse
Loads and manages environment configuration
"""

import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()


class Config:
    """Base configuration"""
    
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    API_TITLE: str = "Metin2 Market Data Warehouse API"
    API_VERSION: str = "1.0.0"
    
    # Database Configuration
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "metin2_warehouse")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    
    @classmethod
    def get_db_connection_string(cls) -> str:
        """Get PostgreSQL connection string"""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

    @classmethod
    def get_db_connection_string_sqlalchemy(cls) -> str:
        """Get SQLAlchemy-compatible PostgreSQL connection string."""
        return f"postgresql+psycopg2://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
    
    # ETL Configuration
    ETL_BATCH_SIZE: int = int(os.getenv("ETL_BATCH_SIZE", "1000"))
    ETL_MAX_WORKERS: int = int(os.getenv("ETL_MAX_WORKERS", "4"))
    ETL_TIMEOUT_SECONDS: int = int(os.getenv("ETL_TIMEOUT_SECONDS", "3600"))
    
    # Data Configuration
    DATA_IMPORT_PATH: str = os.getenv("DATA_IMPORT_PATH", "./data/imports")
    DATA_EXPORT_PATH: str = os.getenv("DATA_EXPORT_PATH", "./data/exports")
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "./logs/app.log")
    
    # Cache Configuration
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "True").lower() == "true"
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
    
    # Analysis Configuration
    VOLATILITY_THRESHOLD: float = float(os.getenv("VOLATILITY_THRESHOLD", "20.0"))
    UNDERVALUATION_THRESHOLD: float = float(os.getenv("UNDERVALUATION_THRESHOLD", "0.85"))
    MIN_CONFIDENCE_SCORE: float = float(os.getenv("MIN_CONFIDENCE_SCORE", "50.0"))


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False


class TestingConfig(Config):
    """Testing environment configuration"""
    DEBUG = True
    DB_NAME = "metin2_warehouse_test"
    CACHE_ENABLED = False


# Select configuration based on environment
ENV = os.getenv("ENVIRONMENT", "development").lower()

if ENV == "production":
    config = ProductionConfig()
elif ENV == "testing":
    config = TestingConfig()
else:
    config = DevelopmentConfig()
