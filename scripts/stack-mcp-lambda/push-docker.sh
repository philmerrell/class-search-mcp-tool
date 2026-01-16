#!/usr/bin/env bash
# Push Docker image to ECR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${SCRIPT_DIR}/../common/load-env.sh"

show_config

if [[ -z "${CDK_AWS_ACCOUNT_ID:-}" ]]; then
    log_error "CDK_AWS_ACCOUNT_ID is required for ECR push"
    exit 1
fi

IMAGE_NAME="${CDK_ECR_REPOSITORY_NAME}"
IMAGE_TAG="${CDK_IMAGE_TAG}"
ECR_REGISTRY="${CDK_AWS_ACCOUNT_ID}.dkr.ecr.${CDK_AWS_REGION}.amazonaws.com"
ECR_IMAGE="${ECR_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

# Load image from tar if provided (CI/CD artifact)
log_info "LOAD_TAR env var: '${LOAD_TAR:-}'"
log_info "Current directory: $(pwd)"
log_info "Listing tar files in current directory:"
ls -la *.tar 2>/dev/null || log_info "No .tar files found in current directory"

if [[ -n "${LOAD_TAR:-}" ]]; then
    if [[ -f "${LOAD_TAR}" ]]; then
        log_info "Loading image from: ${LOAD_TAR}"
        docker load -i "${LOAD_TAR}"
    else
        log_error "LOAD_TAR is set but file does not exist: ${LOAD_TAR}"
        exit 1
    fi
else
    log_info "LOAD_TAR not set, assuming image already exists locally"
fi

log_info "Authenticating with ECR..."
aws ecr get-login-password --region "${CDK_AWS_REGION}" | \
    docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# Check if ECR repository exists, create if not
log_info "Checking if ECR repository exists: ${IMAGE_NAME}"
if ! aws ecr describe-repositories --repository-names "${IMAGE_NAME}" --region "${CDK_AWS_REGION}" >/dev/null 2>&1; then
    log_info "ECR repository does not exist. Creating: ${IMAGE_NAME}"
    aws ecr create-repository \
        --repository-name "${IMAGE_NAME}" \
        --region "${CDK_AWS_REGION}" \
        --image-scanning-configuration scanOnPush=true \
        --tags Key=Project,Value="${CDK_PROJECT_PREFIX}" Key=ManagedBy,Value=github-actions

    log_info "Applying lifecycle policy to ECR repository..."
    aws ecr put-lifecycle-policy \
        --repository-name "${IMAGE_NAME}" \
        --region "${CDK_AWS_REGION}" \
        --lifecycle-policy-text '{
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep images tagged with latest, deployed, prod, staging, or release tags",
                    "selection": {
                        "tagStatus": "tagged",
                        "tagPrefixList": ["latest", "deployed", "prod", "staging", "v", "release"],
                        "countType": "imageCountMoreThan",
                        "countNumber": 999
                    },
                    "action": {
                        "type": "expire"
                    }
                },
                {
                    "rulePriority": 2,
                    "description": "Delete untagged images after 7 days",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 7
                    },
                    "action": {
                        "type": "expire"
                    }
                }
            ]
        }'

    log_info "ECR repository created successfully"
else
    log_info "ECR repository already exists: ${IMAGE_NAME}"
fi

log_info "Tagging image for ECR: ${ECR_IMAGE}"
docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${ECR_IMAGE}"

log_info "Pushing image to ECR..."
docker push "${ECR_IMAGE}"

log_info "Image pushed successfully: ${ECR_IMAGE}"

# Output the image URI for downstream jobs
echo "ecr_image_uri=${ECR_IMAGE}" >> "${GITHUB_OUTPUT:-/dev/null}"
