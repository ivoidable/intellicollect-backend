# AWS Billing Intelligence Backend

A FastAPI-based backend service for intelligent billing and payment processing using AWS services.

## 🚀 Features

- **RESTful API** - Built with FastAPI for high performance
- **AWS Integration** - EventBridge, DynamoDB, and other AWS services
- **Event-Driven Architecture** - Real-time event processing
- **Risk Assessment** - AI-powered risk analysis
- **Payment Processing** - Comprehensive payment handling
- **Customer Management** - Full customer lifecycle management
- **Analytics & Reporting** - Business intelligence dashboards
- **Communication System** - Multi-channel customer communications

## 🛠️ Tech Stack

- **Framework**: FastAPI 0.116.2
- **Runtime**: Python 3.8+
- **Database**: AWS DynamoDB
- **Events**: AWS EventBridge
- **Authentication**: JWT tokens
- **Logging**: Structured logging with structlog
- **Testing**: pytest with async support
- **Code Quality**: Black, flake8, mypy

## 📁 Project Structure

```
backend/
├── app/                     # Main application package
│   ├── api/                 # API endpoints
│   │   └── v1/             # API version 1
│   │       ├── endpoints/   # Individual endpoint modules
│   │       └── router.py    # Main API router
│   ├── core/                # Core functionality
│   │   ├── config.py        # Configuration settings
│   │   ├── logging.py       # Logging configuration
│   │   └── exceptions.py    # Exception handling
│   ├── models/              # Data models
│   ├── services/            # Business logic services
│   │   └── aws/            # AWS service integrations
│   ├── repositories/        # Data access layer
│   └── dynamodb/           # DynamoDB utilities
├── lambda_functions/        # AWS Lambda functions
├── deploy/                  # Deployment configurations
├── tests/                   # Test suite
├── main.py                  # Application entry point
└── requirements.txt         # Python dependencies
```

## 🔧 Installation & Setup

### Prerequisites

- Python 3.8 or higher
- AWS CLI configured with appropriate credentials
- AWS account with necessary permissions

### Environment Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your AWS credentials and configuration
   ```

### Required Environment Variables

```bash
# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Application Settings
APP_NAME="AWS Billing Intelligence Backend"
APP_ENV=development
DEBUG=true
HOST=0.0.0.0
PORT=8000
API_VERSION=v1

# CORS Settings
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8080"]
CORS_ALLOW_CREDENTIALS=true

# Security
SECRET_KEY=your_secret_key_here
JWT_SECRET_KEY=your_jwt_secret_key
```

## 🚀 Running the Application

### Development Server

```bash
# Start development server with auto-reload
python main.py

# Or use uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Production

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at:
- **API Documentation**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **Health Check**: http://localhost:8000/health

## 📊 API Endpoints

### Core Resources

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/customers` | GET, POST | Customer management |
| `/api/invoices` | GET, POST | Invoice operations |
| `/api/payments` | GET, POST | Payment processing |
| `/api/risk` | GET, POST | Risk assessment |
| `/api/communications` | GET, POST | Customer communications |
| `/api/analytics` | GET | Business analytics |

### System Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | API information |

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -v
```

## 📝 Code Quality

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

## 🏗️ AWS Infrastructure

### Required AWS Services

- **DynamoDB**: Customer and transaction data storage
- **EventBridge**: Event-driven architecture
- **Lambda**: Serverless processing functions
- **IAM**: Access control and permissions

### DynamoDB Tables

- `customers` - Customer information
- `invoices` - Invoice records
- `payments` - Payment transactions
- `risk_assessments` - Risk analysis data
- `communications` - Communication logs

## 🔄 Event-Driven Architecture

The system uses AWS EventBridge for decoupled, event-driven communication:

### Event Types

- `InvoiceCreated` - New invoice generated
- `PaymentReceived` - Payment processed
- `RiskAssessmentCompleted` - Risk analysis finished
- `CommunicationSent` - Customer communication delivered
- `CustomerUpdated` - Customer data modified

### Event Flow

```
API Request → Business Logic → EventBridge → Lambda Functions → Downstream Processing
```

## 📈 Monitoring & Logging

- **Structured Logging**: JSON-formatted logs with contextual information
- **Health Checks**: Built-in health monitoring endpoints
- **AWS CloudWatch**: Metrics and log aggregation
- **Error Tracking**: Comprehensive error handling and reporting

## 🔒 Security

- **Input Validation**: Pydantic models for request validation
- **CORS Configuration**: Configurable cross-origin resource sharing
- **Rate Limiting**: API rate limiting middleware
- **Environment Isolation**: Separate configurations for different environments

## 🚀 Deployment

### AWS Lambda

Deploy individual functions:
```bash
cd lambda_functions/
# Package and deploy using AWS CLI or SAM
```

### Container Deployment

```bash
# Build Docker image
docker build -t billing-backend .

# Run container
docker run -p 8000:8000 billing-backend
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For questions or issues:
1. Check the API documentation at `/api/docs`
2. Review the logs for error details
3. Open an issue in the repository

## 🔧 Configuration

### Logging Configuration

The application uses structured logging. Configure log levels in the environment:

```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### AWS Configuration

Ensure your AWS credentials have the following permissions:
- DynamoDB: Full access to application tables
- EventBridge: Put events and manage rules
- Lambda: Execute and manage functions
- CloudWatch: Logs and metrics access

## 📊 Performance

- **Response Times**: < 100ms for most endpoints
- **Throughput**: Scales with AWS Lambda concurrency
- **Availability**: 99.9% uptime with proper AWS configuration

## 🧰 Development Tools

- **FastAPI**: Modern Python web framework
- **Pydantic**: Data validation using Python type annotations
- **structlog**: Structured logging for better observability
- **pytest**: Testing framework with async support
- **Black**: Code formatting
- **mypy**: Static type checking