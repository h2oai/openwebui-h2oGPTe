---
noteId: "3214fe808d4211f095a3695d1fd87cdb"
tags: []

---

# OpenWebUI + H2O GPTe Integration

🚀 **One-Command Startup:** Get OpenWebUI with H2O GPTe pipelines running instantly!

## 🎯 Quick Start

### Option 1: Using the startup script (Recommended)

```bash
./start.sh
```

### Option 2: Using Make

```bash
make install  # Setup and start everything
# OR
make start    # Just start the services
```

### Option 3: Using Docker Compose

```bash
docker-compose up -d
```

**Access your services at:**

- 🌐 **OpenWebUI**: http://localhost:3000
- 🔧 **Pipelines API**: http://localhost:9090

## 📋 Available Commands

### Startup Script Commands

```bash
./start.sh                    # Start everything (default)
./start.sh start              # Start all services
./start.sh stop               # Stop all services  
./start.sh restart            # Restart all services
./start.sh logs               # View logs
./start.sh clean              # Clean up everything
./start.sh help               # Show help
```

### Make Commands

```bash
make help                     # Show all available commands
make start                    # Start all services
make stop                     # Stop all services
make restart                  # Restart all services
make logs                     # View all logs
make clean                    # Clean up containers and volumes
make setup                    # Check dependencies and setup
make install                  # Complete setup + start
make status                   # Show service status
make update                   # Update container images
```

## ⚙️ First-Time Setup

1. Run `./start.sh` to start everything
2. Visit http://localhost:3000 and create an admin account
3. Go to **Admin Panel > Settings > Connections**
4. Add pipeline URL: `http://host.docker.internal:9090`
5. Configure your H2O GPTe settings in the pipeline

## 📦 What Gets Started

1. **OpenWebUI Container**: The main web interface
2. **Pipelines Container**: H2O GPTe pipeline integration
3. **Shared Volumes**: For data persistence and file sharing
4. **Network**: Isolated network for container communication

## 🔧 Prerequisites

- Docker and Docker Compose
- Available ports: 3000 (OpenWebUI), 9090 (Pipelines)

The startup script will check for these dependencies automatically.

## 🐛 Troubleshooting

### Services won't start

```bash
./start.sh clean    # Clean everything
./start.sh start    # Try again
```

### Check service status

```bash
make status
# OR
docker-compose ps
```

### View logs

```bash
make logs           # All services
make logs-web       # OpenWebUI only
make logs-pipeline  # Pipelines only
```

### Port conflicts

If ports 3000 or 9090 are in use, modify `docker-compose.yaml`:

```yaml
ports:
  - "8080:8080"  # Change 3000 to 8080
```

## 🔄 Updates

Update to latest versions:

```bash
make update
make restart
```

## 🛑 Cleanup

Remove everything (containers, volumes, data):

```bash
./start.sh clean
# OR
make clean
```

## 📁 Project Structure

```text
openwebui-h2oGPTe/
├── start.sh              # One-command startup script
├── Makefile               # Make commands for easy management  
├── docker-compose.yaml    # Container orchestration
├── README.md              # This file
└── pipelines/             # H2O GPTe pipeline files
    ├── h2o_pipelinev2_docker.py
    ├── h2opipelinev2.py
    ├── h2opipelinev3.py
    └── h2opipilenev1.py
```

## 📖 Advanced Usage

### H2O GPTe Pipeline Configuration

The project includes several pipeline versions:

- `h2o_pipelinev2_docker.py` - Docker-optimized pipeline
- `h2opipelinev2.py` - Standard pipeline v2
- `h2opipelinev3.py` - Latest pipeline version
- `h2opipilenev1.py` - Legacy pipeline v1

### Environment Variables

Customize your setup with these environment variables:

```bash
# In your shell or .env file
export WEBUI_SECRET_KEY="your-custom-secret-key"
export PIPELINES_API_KEY="your-custom-api-key"
```

### Pipeline Development

To develop custom pipelines:

1. Place your pipeline files in the `pipelines/` directory
2. They'll be automatically mounted into the pipelines container
3. Restart the pipelines service: `docker-compose restart pipelines`

## 🔗 Integration Details

### Connecting to OpenWebUI

1. After startup, visit http://localhost:3000
2. Create an admin account (first-time only)
3. Navigate to **Admin Panel > Settings > Connections**
4. Add connection:
   - **URL**: `http://host.docker.internal:9090`
   - **API Key**: Check your console output or use default

### Pipeline Upload

1. Go to **Pipelines** section in OpenWebUI
2. Upload your H2O pipeline file from the `pipelines/` directory
3. Configure pipeline settings as needed
4. Start using H2O GPTe through OpenWebUI interface

---

*Ready to start? Just run `./start.sh` and you're good to go!* 🎉