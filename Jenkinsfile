// This is a declarative Jenkins Pipeline script for a Docker-based application.

// Set the agent to "any" to run the pipeline on the local Jenkins node
// which is the Azure VM itself.
pipeline {
    agent any

    // Define environment variables for the pipeline
    environment {
        // You can set the full repository URL here or configure it in the Jenkins job settings.
        // For security, it's often better to configure credentials and URL in the job itself.
        // Replace with your GitHub repository URL.
        GIT_REPO_URL = 'https://github.com/akl-githu/OCC.git'
    }

    // Define the stages of the pipeline
    stages {
        // Stage 1: Checkout the source code from Git
        stage('Checkout') {
            steps {
                // The 'checkout scm' step automatically checks out the code
                // from the configured Git repository in the job settings.
                echo 'Checking out source code from Git...'
                git branch: 'main', url: "${GIT_REPO_URL}"
            }
        }

        // Stage 2: Build the Docker image
        stage('Build Docker Image') {
            steps {
                script {
                    echo 'Building Docker image...'
                    // Build the Docker image using the Dockerfile
                    sh 'docker build -t your-app-image:latest .'
                }
            }
        }

        // Stage 3: Deploy the application using Docker Compose
        stage('Deploy with Docker Compose') {
            steps {
                script {
                    echo 'Deploying application using docker-compose...'
                    // Stop and remove any existing containers to ensure a clean start.
                    sh 'docker-compose down --timeout 30 || true'
                    // Use docker-compose up to build and start the containers in detached mode (-d).
                    sh 'docker-compose up -d --build --force-recreate'
                }
            }
        }
    }

    // Post-build actions
    post {
        // Always clean up the workspace to free up disk space on the Jenkins VM.
        // This command ensures that the next build starts with a fresh workspace.
        always {
            cleanWs()
            echo 'Workspace cleaned.'
        }
    }
}