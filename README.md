# Test Reports Automation System

Multi-module Maven project for test automation reporting.

## Project Structure

```
java_reports/
├── pom.xml                    # Parent POM
├── .gitignore
├── .env.example
├── README.md
├── test-core/                 # Cucumber runner, step definitions, Selenium POM
├── allure-integration/        # Allure adapter, screenshot/video hooks
├── report-model/             # run-manifest.json DTO + Jackson parser
├── javalin-server/           # Java Javalin web server
├── email-service/            # Simple Java Mail + Thymeleaf
├── jira-service/             # Jira REST API v2 client
├── doors-service/            # DOORS DXL wrapper
├── orchestrator/             # Pipeline stage runner
└── fastapi-server/           # Python FastAPI (requirements.txt)
```

## Modules

| Module | Description |
|--------|-------------|
| `test-core` | Cucumber runner, step definitions, Selenium Page Object Model |
| `allure-integration` | Allure adapter with screenshot and video capture hooks |
| `report-model` | Data Transfer Objects for run-manifest.json with Jackson |
| `javalin-server` | Standalone Javalin web server (no Spring Boot) |
| `email-service` | Email sending with Simple Java Mail + Thymeleaf templates |
| `jira-service` | Jira REST API v2 client for issue creation/updates |
| `doors-service` | DOORS DXL script wrapper for requirements integration |
| `orchestrator` | Pipeline stage runner coordinating all services |
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
mvn allure:serve
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Tech Stack

- **Testing**: Cucumber 7.x, Selenium 4.x, JUnit 5
- **Reporting**: Allure 2.x
- **Java Server**: Javalin 6.x
- **Email**: Simple Java Mail 8.x, Thymeleaf 3.x
- **Integration**: Jira REST API v2, DOORS DXL
- **Python Server**: FastAPI