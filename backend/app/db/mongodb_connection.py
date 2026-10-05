from pymongo import MongoClient
from app.core.config import settings

# MongoDB client
mongo_client = MongoClient(settings.mongodb_url)

# Database
mongo_db = mongo_client[settings.MONGODB_DB]

# Collections
charger_status_collection = mongo_db["charger_status"]
charging_sessions_collection = mongo_db["charging_sessions"]
fault_reports_collection = mongo_db["fault_reports"]
audit_log_collection = mongo_db["audit_log"]


def get_mongodb():
    """Dependency for MongoDB"""
    return mongo_db
