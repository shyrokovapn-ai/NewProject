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

# --- Lab 6: Paste an agenda (Claude on Bedrock). Needs PROJECT_NAME, SITE_ORIGIN, ALERT_EMAIL ---
AI_REGION    ?= us-east-1
PROJECT_NAME ?= new-project
AI_REPO      ?= $(PROJECT_NAME)-agenda-parser
AI_STACK     ?= $(PROJECT_NAME)-ai
AI_TAG       ?= $(shell date +%Y%m%d%H%M%S)
AI_REGISTRY   = $(ACCOUNT_ID).dkr.ecr.$(AI_REGION).amazonaws.com
SITE_ORIGIN  ?=
ALERT_EMAIL  ?=
PARSER_MODEL ?= anthropic.claude-opus-5-5
TEXT         ?=
stack_out = $(shell aws cloudformation describe-stacks --region $(AI_REGION) --stack-name $(AI_STACK) \
  --query "Stacks[0].Outputs[?OutputKey=='$(1)'].OutputValue" --output text 2>/dev/null)

.PHONY: lint test deploy-frontend deploy-backend llm-hello parse deploy-ai ai-user ai-logs

lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run format:check

test:
	cd backend && python -m pytest -q

deploy-frontend:
	cd frontend && npm ci && VITE_API_URL=$(API_URL) VITE_PARSER_URL=$(call stack_out,ParserUrl) \
	  VITE_COGNITO_CLIENT_ID=$(call stack_out,ClientId) VITE_COGNITO_REGION=$(AI_REGION) npm run build
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

llm-hello:
	python backend/scripts/llm_hello.py

parse:
	cd backend && python -m app.ai.agenda "$(TEXT)"

deploy-ai:
	aws ecr describe-repositories --region $(AI_REGION) --repository-names $(AI_REPO) >/dev/null 2>&1 || \
	  aws ecr create-repository --region $(AI_REGION) --repository-name $(AI_REPO) \
	    --tags Key=PROJECT_NAME,Value=$(PROJECT_NAME) >/dev/null
	aws ecr get-login-password --region $(AI_REGION) | docker login --username AWS --password-stdin $(AI_REGISTRY)
	docker build --platform linux/amd64 --provenance=false -f backend/Dockerfile.agenda \
	  -t $(AI_REGISTRY)/$(AI_REPO):$(AI_TAG) backend
	docker push $(AI_REGISTRY)/$(AI_REPO):$(AI_TAG)
	aws cloudformation deploy --region $(AI_REGION) --stack-name $(AI_STACK) --template-file infra/ai.yml \
	  --capabilities CAPABILITY_IAM --tags PROJECT_NAME=$(PROJECT_NAME) \
	  --parameter-overrides ProjectName=$(PROJECT_NAME) ImageUri=$(AI_REGISTRY)/$(AI_REPO):$(AI_TAG) \
	  ParserModel=$(PARSER_MODEL) "AllowedOrigins=$(SITE_ORIGIN),http://localhost:5173" AlertEmail=$(ALERT_EMAIL)
	aws cloudformation describe-stacks --region $(AI_REGION) --stack-name $(AI_STACK) \
	  --query "Stacks[0].Outputs" --output table

# make ai-user USER_EMAIL=you@example.com USER_PASSWORD='Str0ngPass'
ai-user:
	aws cognito-idp admin-create-user --region $(AI_REGION) --user-pool-id $(call stack_out,UserPoolId) \
	  --username $(USER_EMAIL) --message-action SUPPRESS \
	  --user-attributes Name=email,Value=$(USER_EMAIL) Name=email_verified,Value=true
	aws cognito-idp admin-set-user-password --region $(AI_REGION) --user-pool-id $(call stack_out,UserPoolId) \
	  --username $(USER_EMAIL) --password '$(USER_PASSWORD)' --permanent

# the log line for the submission
ai-logs:
	aws logs tail /aws/lambda/$(PROJECT_NAME)-agenda-parser --region $(AI_REGION) --since 1h | grep agenda_parsed
