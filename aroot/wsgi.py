from app import app
import os

# for production
if __name__ == "__main__":
    app.run(host='127.0.0.1', port=os.environ.get("FLASK_SERVER_PORT"), debug=True)
