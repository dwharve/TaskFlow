import logging
import sys
import os
from flask import Flask
from scheduler import TaskScheduler
from database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('scheduler_process')

def create_app():
    """Create a minimal Flask app for database context"""
    app = Flask(__name__)
    
    # Set environment variables
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    from models import db
    db.init_app(app)
    
    # Initialize database and configure session
    init_db(app)
    
    return app

def main():
    logger.info("Starting scheduler process")
    
    # Create minimal Flask app
    app = create_app()
    
    # Initialize scheduler
    scheduler = TaskScheduler()
    scheduler.init_app(app)
    
    try:
        # Start the scheduler
        scheduler.start()
        logger.info("Scheduler started successfully")
        
        # Keep the process running
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Error in scheduler process: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        scheduler.stop()
        logger.info("Scheduler process stopped")

if __name__ == '__main__':
    main() 