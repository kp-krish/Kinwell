#!/usr/bin/env bash
# Build, push and roll out the voice server to ECS Fargate (us-east-2).
# Usage: bash scripts/deploy_voice.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=us-east-2
ACCT=$(aws sts get-caller-identity --query Account --output text)
REPO=$ACCT.dkr.ecr.$REGION.amazonaws.com/heatcheck-voice
TAG=$(git rev-parse --short HEAD)-$(date +%H%M%S)

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCT.dkr.ecr.$REGION.amazonaws.com" >/dev/null
docker build -t "$REPO:$TAG" . 2>&1 | tail -1
docker push "$REPO:$TAG" 2>&1 | tail -1
echo "pushed $REPO:$TAG"

aws cloudformation deploy --region $REGION --stack-name heatcheck-sunhacks-voice \
  --template-file infra/voice.yaml --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides ImageUri="$REPO:$TAG" \
  VpcId=vpc-0befd135bdd328758 \
  "SubnetIds=subnet-0b47abaf80746a5f6,subnet-0d98448ebd44d5012,subnet-04221c240efe99c9d" \
  SecretArn=arn:aws:secretsmanager:us-east-2:$ACCT:secret:heatcheck/app-rfh1tV

for i in $(seq 1 60); do
  s=$(aws ecs describe-services --region $REGION --cluster heatcheck-sunhacks --services hcs-voice \
      --query "services[0].deployments[0].rolloutState" --output text)
  [ "$s" = "COMPLETED" ] && break
  [ "$s" = "FAILED" ] && { echo "rollout FAILED"; exit 1; }
  sleep 10
done
echo "rollout: $s"
curl -s https://d3t20pvqqs9z05.cloudfront.net/health; echo
