#!/bin/bash

# OpenWebUI + H2O GPTe Quick Start Script
# This script provides a one-command startup for the entire application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "  OpenWebUI + H2O GPTe Quick Start"
    echo "========================================"
    echo -e "${NC}"
}

# Check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command -v docker compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        echo "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    print_status "All dependencies found ✓"
}

# Check if Docker is running
check_docker_running() {
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Main startup function
start_application() {
    print_status "Starting OpenWebUI with H2O GPTe pipelines..."
    
    # Pull latest images
    print_status "Pulling latest container images..."
    docker compose pull
    
    # Start services
    print_status "Starting services..."
    docker compose up -d
    
    # Wait for services to be ready
    print_status "Waiting for services to start..."
    sleep 10
    
    # Check if containers are running
    if docker compose ps | grep -q "Up"; then
        print_status "Services started successfully! ✓"
        echo ""
        echo -e "${GREEN}🌐 OpenWebUI:${NC} http://localhost:3000"
        echo -e "${GREEN}🔧 Pipelines API:${NC} http://localhost:9090"
        echo ""
        echo -e "${YELLOW}📝 First-time setup:${NC}"
        echo "   1. Visit http://localhost:3000 and create an admin account"
        echo "   2. Go to Admin Panel > Settings > Connections"
        echo "   3. Add pipeline URL: http://host.docker.internal:9090"
        echo "   4. Configure your H2O GPTe settings in the pipeline"
        echo ""
        echo -e "${GREEN}✨ Ready to use!${NC}"
    else
        print_error "Some services failed to start. Check logs with: docker compose logs"
        exit 1
    fi
}

# Display help
show_help() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  start, -s, --start     Start the application (default)"
    echo "  stop, --stop           Stop all services"
    echo "  restart, --restart     Restart all services"
    echo "  logs, --logs           Show logs"
    echo "  clean, --clean         Clean up containers and volumes"
    echo "  help, -h, --help       Show this help message"
    echo ""
    echo "Quick start: $0"
    echo "             $0 start"
}

# Handle command line arguments
case "${1:-start}" in
    start|-s|--start|"")
        print_header
        check_dependencies
        check_docker_running
        start_application
        ;;
    stop|--stop)
        print_status "Stopping all services..."
        docker compose down
        print_status "All services stopped ✓"
        ;;
    restart|--restart)
        print_status "Restarting all services..."
        docker compose restart
        print_status "All services restarted ✓"
        ;;
    logs|--logs)
        docker compose logs -f
        ;;
    clean|--clean)
        print_warning "This will remove all containers and data. Continue? (y/N)"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            print_status "Cleaning up..."
            docker compose down -v --remove-orphans
            docker system prune -f
            print_status "Cleanup complete ✓"
        else
            print_status "Cleanup cancelled"
        fi
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        print_error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac