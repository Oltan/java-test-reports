pipeline {
  agent any

  environment {
    JAVA_HOME = tool 'JDK21'
    PATH = "${JAVA_HOME}/bin:${PATH}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Setup Java') {
      steps {
        withCredentials([string(credentialsId: 'jira-pat-id', variable: 'JIRA_PAT')]) {
          // Java setup handled by agent label
        }
        sh 'java -version'
      }
    }

    stage('Setup Python') {
      steps {
        sh 'python3 --version'
      }
    }

    stage('Install Python Dependencies') {
      steps {
        sh 'pip install -r fastapi-server/requirements.txt'
      }
    }

    stage('Run Java Tests') {
      steps {
        sh '/home/ol_ta/tools/apache-maven-3.9.9/bin/mvn -B test -pl test-core,jira-service,email-service,doors-service,report-model,allure-integration,javalin-server,orchestrator'
      }
    }

    stage('Run Python Tests') {
      steps {
        sh 'cd fastapi-server && python3 -m pytest tests/ -v'
      }
    }

    stage('Generate Allure Report') {
      steps {
        sh 'allure generate --clean test-core/target/allure-results -o allure-report'
      }
    }
  }

  post {
    always {
      allure includeProperties: false, results: [[path: 'test-core/target/allure-results']]
    }
  }
}
