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
- Python 3.12+ (for fastapi-server)

## Quick Start

```bash
# Validate Maven project
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn validate

# Build all modules
mvn clean install

# Run tests
mvn test

# Generate Allure report
mvn allure:generate --clean
# Serve the report locally (one way)
open allure-report/index.html
# Or use any static file server, e.g.:
# python -m http.server 8080 -d allure-report
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