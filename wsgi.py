import os
import sys
from app import app
from scheduler import scheduler
import multiprocessing
import logging

logger = logging.getLogger(__name__)

def run_scheduler():
    """Run the scheduler in a separate process"""
    try:
        with app.app_context():
            scheduler.init_app(app)
            scheduler.start()
            # Keep the process running
            while True:
                multiprocessing.Event().wait()
    except Exception as e:
        logger.error(f"Scheduler process error: {str(e)}")
        sys.exit(1)

# Only start the scheduler in the main process
if __name__ == '__main__':
    # Check if we're running under gunicorn
    if os.environ.get('SERVER_SOFTWARE', '').startswith('gunicorn'):
        is_master = os.environ.get('GUNICORN_WORKER_ID') == '0'
        
        if is_master:
            # Start scheduler in a separate process
            scheduler_process = multiprocessing.Process(
                target=run_scheduler,
                name='TaskScheduler'
            )
            scheduler_process.daemon = True
            scheduler_process.start()
            logger.info(f"Started scheduler process (PID: {scheduler_process.pid})")
    else:
        # For development/testing, run scheduler in the main process
        with app.app_context():
            scheduler.init_app(app)
            scheduler.start() 