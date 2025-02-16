import os
import logging
from flask import Flask
from models import db
from scheduler import scheduler

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True
)
logger = logging.getLogger(__name__)

# Set third-party loggers to warning level to reduce noise
for logger_name in ['werkzeug', 'sqlalchemy', 'apscheduler']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

def create_app():
    """Create minimal Flask app for scheduler context"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    db.init_app(app)
    
    return app

def main():
    """Main entry point for scheduler process"""
    logger.info("Starting scheduler process")
    
    # Create minimal Flask app for database context
    app = create_app()
    
    # Initialize scheduler with app context
    scheduler.init_app(app)
    
    try:
        with app.app_context():
            # Start the scheduler
            scheduler.start()
            
            # Keep the process running
            try:
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                scheduler.stop()
    except Exception as e:
        logger.error(f"Error in scheduler process: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main() 