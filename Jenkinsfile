pipeline {
  agent any
  parameters {
    choice(name: 'SERVICE', choices: ['user-service', 'product-service', 'order-service'], description: 'Service to deploy')
  }
  environment {
    APP_HOST = 'ubuntu@APP_VM_PRIVATE_IP'
    APP_IP   = 'APP_VM_PRIVATE_IP'
  }
  stages {
    stage('Checkout') {
      steps { git branch: 'main', url: 'https://github.com/yourorg/cinema-booking.git' }
    }
    stage('Lint / Compile') {
      steps { sh "python3 -m py_compile ${params.SERVICE}/main.py" }
    }
    stage('Package') {
      steps { sh "tar czf ${params.SERVICE}.tgz -C ${params.SERVICE} main.py requirements.txt" }
    }
    stage('Deploy') {
      steps {
        sshagent(['app-vm-ssh-key']) {
          sh """
            scp -o StrictHostKeyChecking=no ${params.SERVICE}.tgz \$APP_HOST:/tmp/
            ssh -o StrictHostKeyChecking=no \$APP_HOST '
              sudo mkdir -p /opt/apps/${params.SERVICE} &&
              sudo tar xzf /tmp/${params.SERVICE}.tgz -C /opt/apps/${params.SERVICE} &&
              cd /opt/apps/${params.SERVICE} &&
              (test -d venv || sudo python3 -m venv venv) &&
              sudo venv/bin/pip install -q -r requirements.txt &&
              sudo chown -R appuser:appuser /opt/apps/${params.SERVICE} &&
              sudo systemctl restart cinema@${params.SERVICE}
            '
          """
        }
      }
    }
    stage('Health Check') {
      steps {
        script {
          def ports = ['user-service': 8081, 'product-service': 8082, 'order-service': 8083]
          sh "sleep 8 && curl -f http://\$APP_IP:${ports[params.SERVICE]}/health"
        }
      }
    }
  }
  post { always { cleanWs() } }
}
