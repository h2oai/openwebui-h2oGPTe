# Pipelines Integration with Open WebUI

A comprehensive guide for integrating H2O GPTe pipelines with Open WebUI, enabling seamless connection between your AI services and the Open WebUI interface.

## 🚀 Quick Start

**TL;DR:** Launch two Docker containers, connect them, and enjoy H2O GPTe on Open WebUI!

1. Launch Open WebUI and Pipeline containers
2. Add pipeline to connections in Open WebUI
3. Download and configure the `h2o_pipeline_docker.py` file
4. Configure pipeline variables and optionally provide collection ID
5. Start using H2O GPTe through Open WebUI

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Setup (Recommended)](#quick-setup-recommended)
- [Alternative Setup Methods](#alternative-setup-methods)
- [Integration Steps](#integration-steps)
- [Usage](#usage)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

This project enables integration between H2O GPTe services and Open WebUI through a pipeline architecture. Pipelines act as a bridge, allowing you to connect your AI services to the Open WebUI interface for a seamless user experience.

## 📦 Prerequisites

- Docker and Docker Compose
- Internet connection for downloading container images
- Available ports: 8080 (Open WebUI) and 9099 (Pipelines)

For local development:
- Python 3.8+
- Node.js and npm
- Docker
- Git

## ⚡ Quick Setup (Recommended)

### Step 1: Launch Pipeline Container

```bash
docker run -d -p 9099:9099 \
  --add-host=host.docker.internal:host-gateway \
  -v pipelines:/app/pipelines \
  --name pipelines \
  --restart always \
  ghcr.io/open-webui/pipelines:main
```

### Step 2: Launch Open WebUI Container

```bash
docker run -d -p 8080:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

### Step 3: First-Time Setup

1. Navigate to `http://localhost:8080/`
2. Create an admin account (first-time setup only)

## 🔧 Alternative Setup Methods

### Local Pipeline Installation

If you prefer running pipelines locally:

```bash
# Clone the repository
git clone https://github.com/open-webui/pipelines.git
cd pipelines

# Set up Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Make start script executable and run
chmod +x ./start.sh
./start.sh  # Windows: start.bat
```

### Local Open WebUI Installation

For development purposes:

```bash
# Clone Open WebUI repository
git clone https://github.com/open-webui/open-webui.git
cd open-webui

# Build frontend
npm install
npm run build

# Set up backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Configure the start script** by adding these sections to `./start.sh`:

```bash
# Add conditional Playwright browser installation
if [[ "$(echo "$WEB_LOADER_ENGINE" | tr '[:upper:]' '[:lower:]')" == "playwright" ]]; then
   if [[ -z "${PLAYWRIGHT_WS_URL}" ]]; then
       echo "Installing Playwright browsers..."
       playwright install chromium
       playwright install-deps chromium
   fi
fi

PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"

if [ -z "${CORS_ALLOWED_ORIGIN}" ]; then
 export CORS_ALLOWED_ORIGIN="*"
 echo "cors allowed"
fi
```

Then run: `./start.sh`

## 🔗 Integration Steps

### 1. Connect Pipeline to Open WebUI

1. Open Open WebUI at `http://localhost:8080/`
2. Click on **Profile Icon** → **Settings**
3. Navigate to **Admin Settings** → **Connections**
4. Click the **Plus Icon** to add a new connection
5. Enter connection details:
   - **URL:** `http://host.docker.internal:9099`
   - **API Key:** `0p3n-w3bu!`
6. Click **Save**

### 2. Add H2O Pipeline

1. Go to the **Pipelines** section in Open WebUI
2. Either:
   - Select the `h2o_pipeline_docker.py` file from your local system, or
   - Provide the GitHub URL to the pipeline file
3. Click the **Upload** button
4. Configure the pipeline settings on the configuration page

## 🎮 Usage

Once integrated, you can:

- Access H2O GPTe functionality through the Open WebUI interface
- Configure pipeline variables as needed
- Optionally provide collection IDs for specific use cases
- Enjoy seamless AI interactions through the web interface

## ⚙️ Configuration

### Pipeline Configuration

When uploading the H2O pipeline, you can configure:

- **Pipeline Variables:** Customize behavior and settings
- **Collection ID:** (Optional) Specify document collections for enhanced context
- **API Endpoints:** Configure H2O GPTe service connections

## 🐛 Troubleshooting

### Common Issues

**Pipeline Connection Failed:**
- Verify both containers are running: `docker ps`
- Check if ports 8080 and 9099 are available
- For Docker setup, use `http://host.docker.internal:9099` as the connection URL
- For local setup, use `http://0.0.0.0:9099` or `http://localhost:9099`
- Ensure API key is correct: `0p3n-w3bu!`
- Restart the Pipeline Docker Container after First importing the pipeline

**Permission Denied (Local Setup):**
```bash
chmod +x ./start.sh
```

**Port Conflicts:**
```bash
# Check port usage
netstat -tulpn | grep :8080
netstat -tulpn | grep :9099
```

**CORS Errors:**
- Verify `CORS_ALLOWED_ORIGIN` is set to `*` or appropriate domain
- Restart containers after configuration changes

### Debug Commands

```bash
# Check container logs
docker logs open-webui
docker logs pipelines

# Restart containers
docker restart open-webui pipelines

# Check container status
docker ps -a
```

### Network Issues

If containers can't communicate:
```bash
# Verify Docker network
docker network ls
docker network inspect bridge
```

## 📁 Project Structure

```
├── README.md
├── pipelines/
│   ├── h2o_pipeline_docker.py
│   ├── requirements.txt
│   └── start.sh
├── open-webui/
│   ├── backend/
│   ├── frontend/
│   └── docker-compose.yml
└── docs/
    └── setup-guide.md
```

## 🔗 Useful Links

- [Open WebUI Repository](https://github.com/open-webui/open-webui)
- [Pipelines Repository](https://github.com/open-webui/pipelines)
- [H2O GPTe Documentation](https://docs.h2o.ai/)

## 📝 Notes

- Pipeline service runs on `http://0.0.0.0:9099`
- Open WebUI runs on `http://localhost:8080/`
- **Docker Connection URL:** `http://host.docker.internal:9099`
- **Local Connection URL:** `http://0.0.0.0:9099` or `http://localhost:9099`
- Default API key for pipeline connection: `0p3n-w3bu!`
- Admin account creation required on first Open WebUI access


---

**Happy AI Development! 🎉**

For additional support, please refer to the official Open WebUI and Pipelines documentation.