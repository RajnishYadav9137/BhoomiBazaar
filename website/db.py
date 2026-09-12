import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "rajnish@123",
    "database": "mywebsite"
}

def get_db():
    """Returns a new MySQL database connection."""
    return mysql.connector.connect(**DB_CONFIG)
