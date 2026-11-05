pipeline {
    agent any

    environment {
        PROJECT_DIR = "${WORKSPACE}"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate Project Structure') {
            steps {
                sh '''
                    test -f user-service/main.py
                    test -f product-service/main.py
                    test -f order-service/main.py

                    test -f frontend/index.html
                    test -f frontend/style.css
                    test -f frontend/app.js

                    test -f deploy/db-setup.sql

                    echo "Project structure validation successful"
                '''
            }
        }

        stage('Python Syntax Check') {
            steps {
                sh '''
                    python3 -m py_compile \
                        user-service/main.py \
                        product-service/main.py \
                        order-service/main.py

                    echo "Python syntax validation successful"
                '''
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    python3 -m venv .venv-user
                    .venv-user/bin/pip install \
                        -r user-service/requirements.txt

                    python3 -m venv .venv-product
                    .venv-product/bin/pip install \
                        -r product-service/requirements.txt

                    python3 -m venv .venv-order
                    .venv-order/bin/pip install \
                        -r order-service/requirements.txt
                '''
            }
        }
    }

    post {
        success {
            echo 'Cinema Booking CI pipeline completed successfully!'
        }

        failure {
            echo 'Cinema Booking CI pipeline failed. Check Console Output.'
        }
    }
}
