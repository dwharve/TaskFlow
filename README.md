# TaskFlow

## Overview
This application is a modular automation platform built with Flask, featuring a block-based architecture for flexible workflow creation and automation.

## Core Functionalities
- User Authentication and Management
- Block-Based Workflow Management
- Task Scheduling and Monitoring
- Data Processing and Transformation
- Action Execution (Email, Webhooks)

## Documentation

### Block Architecture
The application uses a modular block-based system with three main types of blocks:
1. Input Blocks
   - JSON Fetcher: Retrieves data from external APIs or endpoints
   - (More input blocks can be added)

2. Processing Blocks
   - JSON Transformer: Processes and transforms JSON data
   - Item Monitor: Monitors items and their states
   - (More processing blocks can be added)

3. Action Blocks
   - Email Sender: Sends email notifications
   - Webhook Caller: Makes HTTP calls to external endpoints
   - (More action blocks can be added)

### Task Management
- Create, edit, and monitor automation tasks
- Configure block parameters and connections
- Schedule tasks with flexible timing options
- View task execution history and results
- Real-time task status monitoring

### User Interface
- Modern dashboard for task overview
- Task creation and editing forms
- Block configuration interface
- Task execution monitoring
- Responsive design for various screen sizes

### Database
- Supports task and block configuration storage
- Maintains execution history and results
- Tracks block states and configurations
- Migration support for schema updates

### File Structure
```
├── app.py              # Main application file
├── models.py           # Database models
├── scheduler.py        # Task scheduling system
├── blocks/            # Block system implementation
│   ├── manager.py     # Block management
│   ├── input/         # Input blocks
│   ├── processing/    # Processing blocks
│   └── action/        # Action blocks
├── templates/         # HTML templates
│   ├── base.html      # Base template
│   ├── dashboard.html # Main dashboard
│   ├── tasks.html     # Task listing
│   ├── blocks.html    # Block management
│   └── ...           # Other templates
├── static/           # Static assets
│   └── js/          # JavaScript files
└── migrations/       # Database migrations
```

### Setup and Installation

#### Traditional Setup
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Initialize the database
4. Configure environment variables if needed
5. Run the application: `python app.py`

#### Docker Setup
1. Build the Docker image:
   ```bash
   docker build -t taskflow .
   ```

2. Run the container:
   ```bash
   docker run -d -p 5000:5000 taskflow
   ```

3. Environment Variables:
   - `SECRET_KEY`: Application secret key (auto-generated if not provided)
   - `DATABASE_URL`: Database connection URL (default: SQLite)
   - `LOG_LEVEL`: Logging level (default: INFO)
   - `WORKERS`: Number of Gunicorn workers (default: 4)
   - `TIMEOUT`: Gunicorn timeout in seconds (default: 120)

   Example with custom configuration:
   ```bash
   docker run -d \
     -p 5000:5000 \
     -e LOG_LEVEL=WARNING \
     -e WORKERS=2 \
     -e TIMEOUT=60 \
     -e DATABASE_URL=postgresql://user:pass@host/db \
     taskflow
   ```

4. Persistence:
   To persist data between container restarts, mount a volume for the SQLite database:
   ```bash
   docker run -d \
     -p 5000:5000 \
     -v $(pwd)/data:/app/instance \
     taskflow
   ```

5. Production Deployment:
   - Uses Gunicorn as the WSGI server
   - Implements proper logging configuration
   - Runs as non-root user for security
   - Multi-stage build for smaller image size
   - Includes health checks and proper signal handling

### Configuration
- Database settings
- Email configuration (for email actions)
- API keys and external service credentials
- Scheduling parameters
- CSRF protection settings
- Session security configuration
- Template filters and extensions

### Security
- User authentication required
- Secure storage of sensitive data
- API key management
- Password hashing
- CSRF protection on all forms and AJAX requests
- Secure session management

### Templates
- Base template with common layout and navigation
- Jinja2 template inheritance
- Custom filters for date formatting and status badges
- Responsive design with Bootstrap 5
- Dynamic content updates using AJAX
- Standardized error handling and user feedback

### Extensibility
New blocks can be added by:
1. Creating a new block class in the appropriate directory
2. Implementing required interfaces
3. Registering the block with the block manager

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License
[Insert License Information]


