pipeline {
  agent any
  options { disableConcurrentBuilds() }
  environment {
    IMAGE     = 'shwetak1275/quizitout'          // <dockerhub-username>/quizitout
    DOCKERHUB = credentials('dockerhub')        // creates DOCKERHUB_USR / DOCKERHUB_PSW
    LAST_GOOD = "${JENKINS_HOME}/quizitout_last_good"
    // Homebrew Jenkins on macOS starts with PATH=/usr/bin:/bin:/usr/sbin:/sbin, but Docker Desktop
    // installs docker + its credential helper in ~/.docker/bin. Extra dirs are harmless elsewhere.
    PATH      = "${env.HOME}/.docker/bin:/usr/local/bin:/opt/homebrew/bin:${env.PATH}"
  }
  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script { env.TAG = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim() }
      }
    }
    stage('Build test image') {
      steps { sh 'docker build --target test -t $IMAGE:test-$TAG .' }
    }
    stage('Lint') {
      steps { sh 'docker run --rm $IMAGE:test-$TAG ruff check app tests scripts' }
    }
    stage('Unit + API tests') {
      steps { sh 'docker run --rm $IMAGE:test-$TAG' }
    }
    stage('Quality gate') {
      steps { sh 'docker run --rm $IMAGE:test-$TAG python -m scripts.quality_gate' }
    }
    stage('Copilot: lint + tests') {
      steps {
        sh '''
          docker build --target test -t incidentpilot-copilot:test-$TAG ops/copilot
          docker run --rm incidentpilot-copilot:test-$TAG ruff check app tests
          docker run --rm incidentpilot-copilot:test-$TAG
        '''
      }
    }
    stage('Build runtime image') {
      steps { sh 'docker build --target runtime --build-arg GIT_SHA=$TAG -t $IMAGE:$TAG -t $IMAGE:latest .' }
    }
    stage('Trivy scan') {
      steps {
        sh '''
          docker run --rm \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v trivy-cache:/root/.cache/ \
            aquasec/trivy:latest image \
            --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed \
            --timeout 15m \
            $IMAGE:$TAG
        '''
      }
    }
    stage('Copilot: Trivy') {
      steps {
        sh '''
          docker build --target runtime -t incidentpilot-copilot:ci ops/copilot
          docker run --rm \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v trivy-cache:/root/.cache/ \
            aquasec/trivy:latest image \
            --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed \
            --timeout 15m \
            incidentpilot-copilot:ci
        '''
      }
    }
    stage('Push') {
      steps {
        sh '''
          # separate docker config so the pipeline login doesn't overwrite Docker Desktop's login.
          # Pin the daemon address first: the empty config has no context, and Docker Desktop's
          # socket isn't at the default /var/run/docker.sock on macOS.
          export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
          export DOCKER_CONFIG="$WORKSPACE/.docker-push"
          mkdir -p "$DOCKER_CONFIG"
          echo "$DOCKERHUB_PSW" | docker login -u "$DOCKERHUB_USR" --password-stdin
          docker push $IMAGE:$TAG
          docker push $IMAGE:latest
          docker logout
        '''
      }
    }
    stage('Deploy') {
      steps { sh 'IMAGE_TAG=$TAG docker compose -p quizitout up -d' }
    }
    stage('Smoke test') {
      steps {
        sh '''
          CID=$(docker compose -p quizitout ps -q app)
          for i in $(seq 1 20); do
            STATUS=$(docker inspect -f '{{.State.Health.Status}}' $CID)
            [ "$STATUS" = "healthy" ] && break
            sleep 3
          done
          [ "$STATUS" = "healthy" ] || { echo "App never became healthy"; exit 1; }
          docker compose -p quizitout exec -T app python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/quiz/demo')"
        '''
      }
    }
    stage('Record deploy') {
      // Tells the IncidentPilot copilot which release is live and which files it changed.
      // Never fails the build: if the copilot is down we only print a warning.
      steps {
        sh '''
          # $LAST_GOOD still holds the PREVIOUS good sha here ('post success' updates it later)
          PREV=""
          [ -f "$LAST_GOOD" ] && PREV=$(cat "$LAST_GOOD")
          FILES=""
          if [ -n "$PREV" ] && [ "$PREV" != "$TAG" ] && git cat-file -e "$PREV^{commit}" 2>/dev/null; then
            FILES=$(git diff --name-only "$PREV" "$TAG" | paste -s -d, - || true)
          fi
          [ -n "$FILES" ] || FILES=$(git diff-tree --no-commit-id --name-only -r "$TAG" | paste -s -d, - || true)
          MSG=$(git log -1 --format=%s "$TAG" || true)
          curl -fsS --max-time 10 -X POST http://localhost:8001/deploys \
            --data-urlencode "sha=$TAG" \
            --data-urlencode "image=$IMAGE:$TAG" \
            --data-urlencode "commit_message=$MSG" \
            --data-urlencode "files_changed=$FILES" \
            --data-urlencode "status=succeeded" \
            --data-urlencode "kind=deploy" \
          || echo "WARNING: copilot unreachable, deploy not recorded"
        '''
      }
    }
  }
  post {
    success { sh 'echo $TAG > $LAST_GOOD' }
    failure {
      sh '''
        if [ -f "$LAST_GOOD" ]; then
          echo "Rolling back to $(cat $LAST_GOOD)"
          IMAGE_TAG=$(cat $LAST_GOOD) docker compose -p quizitout up -d
          # best effort: let the copilot know which version is live again
          curl -fsS --max-time 10 -X POST http://localhost:8001/deploys \
            --data-urlencode "sha=$(cat $LAST_GOOD)" \
            --data-urlencode "image=$IMAGE:$(cat $LAST_GOOD)" \
            --data-urlencode "commit_message=automatic rollback after failed build" \
            --data-urlencode "files_changed=" \
            --data-urlencode "status=succeeded" \
            --data-urlencode "kind=rollback" \
          || echo "WARNING: copilot unreachable, rollback not recorded"
        else
          echo "No previous good version to roll back to"
        fi
      '''
    }
    always { sh 'docker image prune -f || true' }
  }
}
