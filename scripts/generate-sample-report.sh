#!/bin/bash
# Generate sample Allure report for verification
# This script runs the AllureVerificationTest and generates an HTML report

set -e

export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:/home/ol_ta/tools/allure-2.33.0/bin:$PATH"

cd /mnt/c/Users/ol_ta/desktop/java_reports

echo "Running Maven tests for test-core (AllureVerificationTest)..."
mvn -q -pl test-core test -Dtest="AllureVerificationTest"

echo "Generating Allure report..."
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

if test -f test-core/target/allure-report/index.html; then
    echo "SUCCESS: Allure report generated at test-core/target/allure-report/index.html"
else
    echo "ERROR: Allure report index.html not found"
    exit 1
fi
