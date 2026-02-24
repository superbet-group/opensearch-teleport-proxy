# OpenSearch Teleport Proxy

A multi-cluster HTTP proxy for accessing OpenSearch instances through Teleport with client certificate authentication.

## Overview

This proxy allows you to connect to OpenSearch clusters secured behind Teleport by:
- Running a local HTTP proxy that forwards requests to HTTPS Teleport apps
- Using client certificates from `tsh` for authentication
- Supporting multiple clusters simultaneously with different ports

## Features

- Multi-cluster support with JSON configuration
- Automatic certificate discovery from `tsh` keys directory
- Concurrent proxy support for multiple clusters
- Configurable ports and timeouts
- Verbose logging mode for debugging

## Installation

1. Ensure you have Python 3 installed
2. Clone this repository
3. Make the script executable:
```bash
chmod +x opensearch-teleport-proxy.py
```

## Quick Start

### 1. Generate Configuration

```bash
python3 opensearch-teleport-proxy.py --init-config
```

This creates `~/.opensearch-teleport-proxy.json` with sample configuration.

### 2. Configure Your Clusters

Edit `~/.opensearch-teleport-proxy.json` to add your OpenSearch clusters:

```json
{
  "version": "1.0",
  "defaults": {
    "teleport_domain": "teleport.happening.dev",
    "tsh_keys_dir": "~/.tsh/keys/teleport.happening.dev",
    "listen_host": "127.0.0.1",
    "timeout": 60
  },
  "clusters": {
    "my-cluster": {
      "app_name": "opensearch-my-cluster",
      "teleport_url": "https://opensearch-my-cluster.teleport.happening.dev",
      "port": 9243,
      "description": "My OpenSearch Cluster"
    }
  }
}
```

### 3. Login to Teleport

```bash
tsh app login opensearch-my-cluster
```

### 4. Start the Proxy

For a single cluster:
```bash
python3 opensearch-teleport-proxy.py my-cluster
```

For all configured clusters:
```bash
python3 opensearch-teleport-proxy.py --all
```

## Usage Examples

### List Available Clusters
```bash
python3 opensearch-teleport-proxy.py --list
```

### Show Cluster Details
```bash
python3 opensearch-teleport-proxy.py my-cluster --show
```

### Start with Custom Port
```bash
python3 opensearch-teleport-proxy.py my-cluster --port 9999
```

### Enable Verbose Logging
```bash
python3 opensearch-teleport-proxy.py my-cluster --verbose
```

## Configuration

### Configuration File Locations

The proxy searches for configuration files in the following order:
1. Custom path via `--config` flag
2. `OPENSEARCH_PROXY_CONFIG` environment variable
3. `~/.opensearch-teleport-proxy.json`
4. `~/.config/opensearch-teleport-proxy.json`
5. `/etc/opensearch-teleport-proxy.json`
6. `./opensearch-teleport-proxy.json`

### Environment Variables

- `OPENSEARCH_PROXY_CONFIG`: Custom config file path
- `OPENSEARCH_PROXY_PORT`: Override listen port
- `OPENSEARCH_PROXY_TSH_KEYS`: Override tsh keys directory
- `OPENSEARCH_PROXY_TIMEOUT`: Override request timeout
- `OPENSEARCH_PROXY_VERBOSE`: Enable verbose logging (1, true, yes)

### Configuration Schema

```json
{
  "version": "1.0",
  "defaults": {
    "teleport_domain": "teleport.example.com",
    "tsh_keys_dir": "~/.tsh/keys/teleport.example.com",
    "listen_host": "127.0.0.1",
    "timeout": 60
  },
  "clusters": {
    "cluster-name": {
      "app_name": "teleport-app-name",
      "teleport_url": "https://app.teleport.example.com",
      "port": 9243,
      "description": "Optional description"
    }
  }
}
```

## MCP Server Integration

After starting the proxy, configure your MCP server with:

```bash
OPENSEARCH_URL=http://127.0.0.1:<port>
OPENSEARCH_NO_AUTH=true
```

For example, if your cluster runs on port 9243:
```bash
OPENSEARCH_URL=http://127.0.0.1:9243
OPENSEARCH_NO_AUTH=true
```

## Troubleshooting

### Certificate Not Found

If you see "Certificate not found" errors:
1. Verify you're logged in: `tsh status`
2. Login to the app: `tsh app login <app-name>`
3. Check certificates: `ls -la ~/.tsh/keys/*/teleport.*/`

### Port Already in Use

If the port is already in use:
1. Stop the other process: `lsof -ti:<port> | xargs kill`
2. Or use a different port: `--port 9999`
3. Or update the config file to use a different port

### Connection Timeout

If requests timeout:
- Increase timeout in config: `"timeout": 120`
- Or use environment variable: `OPENSEARCH_PROXY_TIMEOUT=120`
- Check your Teleport session: `tsh status`

## License

MIT
