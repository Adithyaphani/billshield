#!/usr/bin/env bash
# Deploy BillShield to AWS App Runner via ECR.
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Docker running locally
#
# Usage: ./deploy/ship.sh [region]

set -euo pipefail

REGION="${1:-us-east-1}"
APP="billshield"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REPO="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${APP}"

echo "==> Account ${ACCOUNT}, region ${REGION}"

# 1. ECR repository
aws ecr describe-repositories --repository-names "${APP}" --region "${REGION}" \
  >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${APP}" --region "${REGION}" \
       --image-scanning-configuration scanOnPush=true >/dev/null
echo "==> ECR repository ready"

# 2. Build and push
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

docker build --platform linux/amd64 -t "${APP}:latest" .
docker tag "${APP}:latest" "${REPO}:latest"
docker push "${REPO}:latest"
echo "==> Image pushed to ${REPO}:latest"

# 3. IAM role App Runner uses to pull from ECR
ROLE="AppRunnerECRAccessRole"
if ! aws iam get-role --role-name "${ROLE}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${ROLE}" \
    --assume-role-policy-document '{
      "Version":"2012-10-17",
      "Statement":[{"Effect":"Allow",
        "Principal":{"Service":"build.apprunner.amazonaws.com"},
        "Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "${ROLE}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
  echo "==> Created ${ROLE}; waiting for propagation"
  sleep 15
fi
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"

# 4. Create or update the App Runner service
EXISTING="$(aws apprunner list-services --region "${REGION}" \
  --query "ServiceSummaryList[?ServiceName=='${APP}'].ServiceArn" --output text)"

if [ -z "${EXISTING}" ]; then
  echo "==> Creating App Runner service"
  aws apprunner create-service --region "${REGION}" \
    --service-name "${APP}" \
    --source-configuration "{
      \"AuthenticationConfiguration\":{\"AccessRoleArn\":\"${ROLE_ARN}\"},
      \"AutoDeploymentsEnabled\":true,
      \"ImageRepository\":{
        \"ImageIdentifier\":\"${REPO}:latest\",
        \"ImageRepositoryType\":\"ECR\",
        \"ImageConfiguration\":{\"Port\":\"8080\"}}}" \
    --health-check-configuration '{
      "Protocol":"HTTP","Path":"/api/v1/health",
      "Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}' \
    --instance-configuration '{"Cpu":"1024","Memory":"2048"}' >/dev/null
else
  echo "==> Updating existing service"
  aws apprunner start-deployment --region "${REGION}" --service-arn "${EXISTING}" >/dev/null
fi

echo "==> Waiting for the service to come up (this takes a few minutes)"
for _ in $(seq 1 60); do
  ARN="$(aws apprunner list-services --region "${REGION}" \
    --query "ServiceSummaryList[?ServiceName=='${APP}'].ServiceArn" --output text)"
  STATUS="$(aws apprunner describe-service --region "${REGION}" \
    --service-arn "${ARN}" --query 'Service.Status' --output text)"
  echo "    status: ${STATUS}"
  [ "${STATUS}" = "RUNNING" ] && break
  [ "${STATUS}" = "CREATE_FAILED" ] && { echo "Deploy failed."; exit 1; }
  sleep 15
done

URL="$(aws apprunner describe-service --region "${REGION}" \
  --service-arn "${ARN}" --query 'Service.ServiceUrl' --output text)"

echo
echo "==> Live at: https://${URL}"
echo "==> Health:  https://${URL}/api/v1/health"
echo "==> API doc: https://${URL}/docs"
echo
echo "Verifying..."
curl -sf "https://${URL}/api/v1/health" && echo " <- health check passed"
