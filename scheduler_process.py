import logging
import sys
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
    
    # Import config from main app
    app.config.from_object('app.config')
    
    # Initialize database
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
        
        # Keep the process running
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Error in scheduler process: {str(e)}", exc_info=True)
    finally:
        scheduler.stop()
        logger.info("Scheduler process stopped")

if __name__ == '__main__':
    main() 