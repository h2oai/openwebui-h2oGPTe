# OpenWebUI + H2O GPTe Integration
![OpenWebUI Demo](demo/OpenWebUI%20Demo_01.gif)

🚀 **One-Command Startup:** Get OpenWebUI with H2O GPTe pipelines running instantly!

## 🎯 Quick Start

### Option 1: Using the startup script (Recommended)
For this one you need to have docker preinstalled. You may need to create a PAT from GitHub to pull the images from the GitHub container registry.

```bash
./start.sh
```

#### 🚀 Complete Setup Guide (After Running start.sh)

Once your Docker containers are running, follow these steps to get H2O GPTe working:

##### Step 1: Access OpenWebUI and Create Admin Account
1. Open your browser and go to: **http://localhost:3000**
2. **Create your first-time admin account** (this only happens once)
3. **Login** with your new admin credentials

##### Step 2: Connect the Pipeline
1. Click on your **profile icon** (top-right corner)
2. Go to **Settings**
3. Navigate to **Admin Settings > Connections**
4. **Add a new connection** with these details:
   - **URL**: `http://host.docker.internal:9090`
   - **API Key**: `0p3n-w3bu!`
5. **Save** the connection

##### Step 3: Configure H2O GPTe Pipeline
1. Stay in **Admin Settings** and go to **Pipelines**
2. You should see the available pipelines listed
3. Find and click on **h2ogpte_pipeline** to configure it
4. **Fill in the required fields**:
   - **URL**: [Your H2O GPTe server URL]
   - **API Key**: [Your H2O GPTe API key]
   - **Collection ID**: [Your collection ID]
   - **Collection Name**: [Your collection name]
5. **Save** the pipeline configuration

##### Step 4: Verify Setup
1. Go back to the main chat interface
2. Check the **Models** dropdown - you should now see **h2ogpte** listed
3. **Select h2ogpte** as your model
4. **Start querying!** 🎉

> **✅ Success Indicator**: When you see "h2ogpte" in your models dropdown, everything is working correctly!

---

### 🔑 GitHub PAT Setup for Private Container Registry

1. Generate a Personal Access Token:  
   `GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token`  
   - Select scopes: `read:packages`, `write:packages` (if pushing), `repo` (if pulling private repos).  

2. Authenticate Docker with your PAT:  

```bash
echo "<YOUR_PAT>" | docker login ghcr.io -u <YOUR_GITHUB_USERNAME> --password-stdin
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

*Ready to start? Just run `./start.sh` and follow the setup guide above!* 🎉