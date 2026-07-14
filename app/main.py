import os
import sys
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

# Δυναμική προσθήκη της ρίζας του project στο sys.path για να παίζει παντού τοπικά
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Εισαγωγή χωρίς το πρόθεμα "app." καθώς βρισκόμαστε ήδη μέσα στο runtime directory
from settings import logger
from database import initialize_mysql
from cache import initialize_redis
from routes import register_blueprints

# 1. Αρχικοποίηση του Flask App
app = Flask(__name__)

# 2. Global Error Handler για Unhandled Exceptions & HTTP Errors
@app.errorhandler(Exception)
def handle_exception(error):
    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code

    logger.exception("Unhandled exception: %s", error)
    return jsonify({"error": "Internal server error"}), 500

# 3. Αρχικοποίηση των Υποδομών κατά το Startup
initialize_mysql()
initialize_redis()

# 4. Καταχώρηση όλων των Blueprints (Routes)
register_blueprints(app)

# 5. Εκκίνηση του Server
if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000"))
    )