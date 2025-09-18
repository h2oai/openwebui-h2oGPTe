.PHONY: help start stop restart logs clean setup install

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

start: ## Start all services (one command startup)
	@echo "🚀 Starting OpenWebUI with H2O GPTe pipelines..."
	@docker-compose up -d
	@echo "✅ Services started successfully!"
	@echo "🌐 OpenWebUI: http://localhost:3000"
	@echo "🔧 Pipelines API: http://localhost:9090"
	@echo ""
	@echo "📝 First-time setup:"
	@echo "   1. Visit http://localhost:3000 and create an admin account"
	@echo "   2. Go to Admin Panel > Settings > Connections"
	@echo "   3. Add pipeline URL: http://host.docker.internal:9090"
	@echo "   3. Add pipeline APIKEY: 0p3n-w3bu!"
	@echo "   4. Configure your H2O GPTe settings in the pipeline"

stop: ## Stop all services
	@echo "🛑 Stopping all services..."
	@docker-compose down
	@echo "✅ All services stopped"

restart: ## Restart all services
	@echo "🔄 Restarting all services..."
	@docker-compose restart
	@echo "✅ All services restarted"

logs: ## View logs from all services
	@docker-compose logs -f

logs-web: ## View OpenWebUI logs
	@docker-compose logs -f openwebui

logs-pipeline: ## View pipeline logs
	@docker-compose logs -f pipelines

clean: ## Remove all containers and volumes (fresh start)
	@echo "🧹 Cleaning up containers and volumes..."
	@docker-compose down -v --remove-orphans
	@docker system prune -f
	@echo "✅ Cleanup complete"

setup: ## Initial setup and dependency check
	@echo "🔧 Checking dependencies..."
	@command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed. Please install Docker first."; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose is required but not installed. Please install Docker Compose first."; exit 1; }
	@echo "✅ All dependencies found"
	@echo "🏗️  Setting up project..."
	@docker-compose pull
	@echo "✅ Setup complete! Run 'make start' to launch the application"

install: setup start ## Complete installation and startup

status: ## Show status of all services
	@docker-compose ps

shell-web: ## Open shell in OpenWebUI container
	@docker-compose exec openwebui /bin/bash

shell-pipeline: ## Open shell in pipelines container
	@docker-compose exec pipelines /bin/bash

update: ## Update all container images
	@echo "📥 Updating container images..."
	@docker-compose pull
	@echo "✅ Images updated. Run 'make restart' to use new versions"