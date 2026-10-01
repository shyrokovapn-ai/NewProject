# fill these in (env vars or `make deploy-backend ECR_REPO=...`). See DEPLOY.md
AWS_REGION   ?= eu-central-1
ECR_REPO     ?= spry-backend
CLUSTER      ?= spry
SERVICE      ?= spry-backend
TASK_FAMILY  ?= spry-backend
BUCKET       ?=
DIST_ID      ?=
API_URL      ?=
TAG          ?= $(shell git rev-parse --short HEAD)

ACCOUNT_ID = $(shell aws sts get-caller-identity --query Account --output text)
REGISTRY   = $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
IMAGE      = $(REGISTRY)/$(ECR_REPO)

.PHONY: lint test deploy-frontend deploy-backend

lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run format:check

test:
	cd backend && python -m pytest -q

deploy-frontend:
	cd frontend && npm ci && VITE_API_URL=$(API_URL) npm run build
	aws s3 sync frontend/dist s3://$(BUCKET) --delete
	aws cloudfront create-invalidation --distribution-id $(DIST_ID) --paths "/*"

deploy-backend:
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(REGISTRY)
	docker build --platform linux/amd64 -t $(IMAGE):$(TAG) backend
	docker push $(IMAGE):$(TAG)
	TD=$$(aws ecs describe-task-definition --task-definition $(TASK_FAMILY) --query taskDefinition \
	  | jq --arg img "$(IMAGE):$(TAG)" 'del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy) | .containerDefinitions[0].image=$$img'); \
	NEW=$$(aws ecs register-task-definition --cli-input-json "$$TD" --query taskDefinition.taskDefinitionArn --output text); \
	aws ecs update-service --cluster $(CLUSTER) --service $(SERVICE) --task-definition $$NEW
