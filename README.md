# Test Reports Automation System

Multi-module Maven project for test automation reporting.

## Project Structure

```
java_reports/
├── pom.xml                    # Parent POM
├── .gitignore
├── .env.example
├── README.md
├── test-core/                 # Cucumber runner, step defs, Selenium POM, Allure hooks

└── fastapi-server/           # Python FastAPI (requirements.txt)
```

## Modules

| Module | Description |
|--------|-------------|
| `test-core` | Cucumber runner, step defs, Selenium POM, Allure hooks (screenshot + video) |

| `fastapi-server` | Python FastAPI server (separate from Maven build) |

## Requirements

- Java 21
- Maven 3.9+
- Python 3.11+ (for fastapi-server)
  - Install server and dev/test dependencies: `cd fastapi-server && pip install -r requirements.txt -r requirements-dev.txt`

## Quick Start

```bash
# Validate Maven project
mvn validate

# Build all modules
mvn clean install

# Run tests
mvn test

# Generate Allure report
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
# Serve the report locally
python3 -m http.server 8080 -d test-core/target/allure-report
# Then visit http://localhost:8080
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Tech Stack

- **Testing**: Cucumber 7.x, Selenium 4.x, JUnit 5
- **Reporting**: Allure 2.x
- **Python Server**: FastAPI