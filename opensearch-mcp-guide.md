# OpenSearch MCP Setup Guide

## Overview

This guide explains how to use the **OpenSearch MCP Server** with Claude Code to query and analyze OpenSearch clusters through Teleport-secured connections.

### What is OpenSearch MCP?

The OpenSearch MCP (Model Context Protocol) server allows Claude Code to interact with OpenSearch clusters directly. It provides tools for:
- Searching indices and querying data
- Analyzing log patterns and distributions
- Managing indices and cluster health
- Performing advanced data analysis

### Architecture

```
┌─────────────┐
│ Claude Code │
│             │
└──────┬──────┘
       │ MCP Protocol
       │
┌──────▼──────────────────────┐
│ OpenSearch MCP Server       │
│ (opensearch-mcp-server-py)  │
└──────┬──────────────────────┘
       │ HTTP
       │
┌──────▼────────────────────────┐
│ Teleport Proxy (Local)        │
│ http://127.0.0.1:9243         │
│ http://127.0.0.1:9244         │
└──────┬────────────────────────┘
       │ HTTPS + Client Certs
       │
┌──────▼─────────────────────────────┐
│ Teleport OpenSearch Apps           │
│ *.teleport.happening.dev           │
└────────────────────────────────────┘
```

The system consists of three layers:
1. **OpenSearch MCP Server** - Manages multiple cluster connections
2. **Local Proxy** - Handles Teleport authentication with client certificates
3. **Teleport Apps** - Secured OpenSearch endpoints

---

## Prerequisites

Before you begin, ensure you have:

- ✅ **Python 3.10+** with `uvx` installed
- ✅ **Teleport CLI** (`tsh`) installed and configured
- ✅ **Access** to Teleport OpenSearch applications
- ✅ **Claude Code** with MCP support enabled

---

## Configuration Files

The setup uses three main configuration files:

### 1. MCP Server Configuration

**Location:** `~/.mcp.json`

This configures Claude Code to use the OpenSearch MCP server:

```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "/Users/ivansrsen/.asdf/installs/python/3.10.3/bin/uvx",
      "args": [
        "opensearch-mcp-server-py",
        "--mode", "multi",
        "--config", "/Users/ivansrsen/.opensearch-mcp-clusters.yml"
      ],
      "env": {}
    }
  }
}
```

**Key fields:**
- `command` - Path to uvx executable
- `args` - Arguments including `--mode multi` for multi-cluster support
- `--config` - Path to cluster configuration file

### 2. OpenSearch Clusters Configuration

**Location:** `~/.opensearch-mcp-clusters.yml`

This defines the OpenSearch clusters accessible through the MCP server:

```yaml
version: "1.0"
description: "OpenSearch Teleport proxy clusters"

clusters:
  trading-topics-qa:
    opensearch_url: "http://127.0.0.1:9243"
    opensearch_no_auth: true

  content-stage:
    opensearch_url: "http://127.0.0.1:9244"
    opensearch_no_auth: true
```

**Key fields:**
- `opensearch_url` - Local proxy URL (points to Teleport proxy)
- `opensearch_no_auth` - Set to `true` (proxy handles authentication)

### 3. Teleport Proxy Configuration

**Location:** `~/.opensearch-teleport-proxy.json`

This configures the local proxy that connects to Teleport:

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
    "trading-topics-qa": {
      "app_name": "opensearch-trading-topics-qa",
      "teleport_url": "https://opensearch-trading-topics-qa.teleport.happening.dev",
      "port": 9243,
      "description": "Trading Topics QA Environment"
    },
    "content-stage": {
      "app_name": "opensearch-content-stage",
      "teleport_url": "https://opensearch-content-stage.teleport.happening.dev",
      "port": 9244,
      "description": "Content Stage Environment"
    }
  }
}
```

**Key fields:**
- `app_name` - Teleport application name (used for `tsh app login`)
- `teleport_url` - HTTPS endpoint for the Teleport application
- `port` - Local port for the proxy
- `tsh_keys_dir` - Directory where Teleport stores client certificates

---

## Initial Setup

### Step 1: Generate Proxy Configuration

If you don't have a proxy config file yet, generate a sample:

```bash
python3 ~/Downloads/opensearch-teleport-proxy.py --init-config
```

This creates `~/.opensearch-teleport-proxy.json` with sample clusters.

### Step 2: Edit Configuration

Edit the generated config to add your clusters:

```bash
vi ~/.opensearch-teleport-proxy.json
```

Add or modify clusters in the `"clusters"` section with:
- Unique cluster name (key)
- `app_name` - The Teleport app name
- `teleport_url` - The full Teleport URL
- `port` - Unique local port for each cluster
- `description` - Human-readable description

### Step 3: Create MCP Clusters Config

Create `~/.opensearch-mcp-clusters.yml`:

```bash
cat > ~/.opensearch-mcp-clusters.yml << 'EOF'
version: "1.0"
description: "OpenSearch Teleport proxy clusters"

clusters:
  your-cluster-name:
    opensearch_url: "http://127.0.0.1:9243"
    opensearch_no_auth: true
EOF
```

Match the cluster names and ports from your proxy config.

### Step 4: Verify MCP Server Config

Ensure `~/.mcp.json` references the correct cluster config file:

```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "/path/to/uvx",
      "args": [
        "opensearch-mcp-server-py",
        "--mode", "multi",
        "--config", "/Users/yourusername/.opensearch-mcp-clusters.yml"
      ],
      "env": {}
    }
  }
}
```

---

## Daily Usage

### Starting the Proxy

You need to start the Teleport proxy before using OpenSearch MCP:

#### Option 1: Single Cluster

```bash
# Login to Teleport app
tsh app login opensearch-trading-topics-qa

# Start proxy for that cluster
python3 ~/Downloads/opensearch-teleport-proxy.py trading-topics-qa
```

#### Option 2: All Clusters (Recommended)

```bash
# Login to all Teleport apps first
tsh app login opensearch-trading-topics-qa
tsh app login opensearch-content-stage

# Start proxies for all clusters
python3 ~/Downloads/opensearch-teleport-proxy.py --all
```

This starts separate proxy processes for each cluster on their configured ports.

### Using with Claude Code

Once the proxies are running:

1. **Open Claude Code** in your terminal
2. **Ask questions** about your OpenSearch data
3. **Use natural language** - Claude will automatically use the appropriate MCP tools

Example queries:
```
- "List all indices in the trading-topics-qa cluster"
- "Search for error logs in the last hour"
- "Analyze log patterns in content-stage cluster"
- "Compare data distribution between clusters"
```

---

## Command Reference

### Proxy Commands

#### List Available Clusters
```bash
python3 opensearch-teleport-proxy.py --list
```

Shows all configured clusters with their ports and descriptions.

#### Show Cluster Details
```bash
python3 opensearch-teleport-proxy.py <cluster-name> --show
```

Displays detailed configuration for a specific cluster.

#### Start Single Cluster Proxy
```bash
python3 opensearch-teleport-proxy.py <cluster-name>
```

Starts proxy on the configured port (e.g., 9243).

#### Start with Custom Port
```bash
python3 opensearch-teleport-proxy.py <cluster-name> --port 9999
```

Overrides the configured port.

#### Start All Cluster Proxies
```bash
python3 opensearch-teleport-proxy.py --all
```

Starts proxies for all configured clusters simultaneously.

#### Verbose Mode
```bash
python3 opensearch-teleport-proxy.py <cluster-name> --verbose
```

Enables detailed logging for debugging.

### Teleport Commands

#### Check Teleport Status
```bash
tsh status
```

Shows current Teleport login status and available apps.

#### Login to App
```bash
tsh app login <app-name>
```

Authenticates and downloads client certificates.

#### List Available Apps
```bash
tsh app ls
```

Shows all Teleport applications you have access to.

---

## Troubleshooting

### Certificate Not Found Error

**Error:**
```
ERROR: Certificate not found for 'opensearch-trading-topics-qa'
```

**Solution:**
1. Verify you're logged in to Teleport:
   ```bash
   tsh status
   ```

2. Login to the specific app:
   ```bash
   tsh app login opensearch-trading-topics-qa
   ```

3. Check certificates exist:
   ```bash
   ls -la ~/.tsh/keys/teleport.happening.dev/*/teleport.happening.dev/
   ```

### Port Already in Use

**Error:**
```
ERROR: Cannot bind to 127.0.0.1:9243 - port already in use
```

**Solution:**

**Option 1:** Kill the existing process
```bash
lsof -ti:9243 | xargs kill
```

**Option 2:** Use a different port
```bash
python3 opensearch-teleport-proxy.py trading-topics-qa --port 9999
```

Then update `~/.opensearch-mcp-clusters.yml` to match the new port.

### Connection Timeout

**Error:**
```
[proxy] ERROR: timed out
```

**Possible causes:**
1. **Teleport session expired** - Run `tsh app login <app-name>` again
2. **Network issues** - Check your VPN/network connection
3. **Timeout too short** - Increase timeout in config:
   ```json
   {
     "defaults": {
       "timeout": 120
     }
   }
   ```

### MCP Server Not Connecting

**Symptoms:**
- Claude Code doesn't see OpenSearch tools
- MCP server errors in logs

**Solutions:**

1. **Verify proxy is running:**
   ```bash
   curl http://127.0.0.1:9243
   ```

2. **Check MCP config path:**
   Ensure `--config` in `.mcp.json` points to the correct file

3. **Test cluster config:**
   ```bash
   cat ~/.opensearch-mcp-clusters.yml
   ```

4. **Restart Claude Code:**
   Restart the Claude Code session to reload MCP servers

### Available Certificates Mismatch

**Error shows certificates but not the one you need:**

```
Available certificates found:
  - opensearch-other-cluster
```

**Solution:**
The `app_name` in your proxy config might not match the Teleport app name.

1. List available Teleport apps:
   ```bash
   tsh app ls
   ```

2. Update `app_name` in `~/.opensearch-teleport-proxy.json` to match exactly

---

## Example Workflows

### Workflow 1: Querying Logs Across Environments

```
You: "Search for errors in the trading-topics-qa cluster from the last 30 minutes"

Claude uses OpenSearch MCP to:
1. List available indices
2. Identify log indices
3. Query for error-level logs
4. Present findings with timestamps and messages
```

### Workflow 2: Comparing Data Distributions

```
You: "Compare the distribution of request types between trading-topics-qa and content-stage"

Claude uses OpenSearch MCP to:
1. Query both clusters
2. Aggregate request types
3. Calculate distributions
4. Present side-by-side comparison
```

### Workflow 3: Pattern Analysis

```
You: "Analyze log patterns in content-stage to identify anomalies"

Claude uses OpenSearch MCP to:
1. Fetch recent logs
2. Use LogPatternAnalysisTool
3. Group similar patterns
4. Identify outliers and unusual sequences
5. Present insights for troubleshooting
```

### Workflow 4: Index Management

```
You: "Show me the health and size of all indices in trading-topics-qa"

Claude uses OpenSearch MCP to:
1. List all indices with detailed info
2. Get index statistics
3. Check shard allocation
4. Present formatted table with size, doc count, and health status
```

---

## Environment Variables

### Proxy Environment Variables

You can override config values using environment variables:

```bash
# Custom config file location
export OPENSEARCH_PROXY_CONFIG=~/custom-config.json

# Override port
export OPENSEARCH_PROXY_PORT=9999

# Override certificate directory
export OPENSEARCH_PROXY_TSH_KEYS=~/.tsh/keys/custom-domain

# Override timeout
export OPENSEARCH_PROXY_TIMEOUT=120

# Enable verbose logging
export OPENSEARCH_PROXY_VERBOSE=true
```

---

## Adding New Clusters

### Step 1: Add to Proxy Config

Edit `~/.opensearch-teleport-proxy.json`:

```json
{
  "clusters": {
    "new-cluster": {
      "app_name": "opensearch-new-cluster",
      "teleport_url": "https://opensearch-new-cluster.teleport.happening.dev",
      "port": 9245,
      "description": "New Cluster Environment"
    }
  }
}
```

### Step 2: Add to MCP Config

Edit `~/.opensearch-mcp-clusters.yml`:

```yaml
clusters:
  new-cluster:
    opensearch_url: "http://127.0.0.1:9245"
    opensearch_no_auth: true
```

### Step 3: Login and Start

```bash
# Login to the new Teleport app
tsh app login opensearch-new-cluster

# Start the proxy
python3 ~/Downloads/opensearch-teleport-proxy.py new-cluster
```

---

## Best Practices

1. **Keep proxies running** - Start with `--all` flag to have all clusters ready
2. **Use unique ports** - Avoid port conflicts by spacing ports (9243, 9244, 9245, etc.)
3. **Refresh Teleport sessions** - Re-login if experiencing auth errors
4. **Match cluster names** - Keep cluster names consistent across all config files
5. **Monitor proxy logs** - Use `--verbose` when troubleshooting
6. **Organize by environment** - Name clusters clearly (qa, stage, prod)

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Initialize config | `python3 opensearch-teleport-proxy.py --init-config` |
| List clusters | `python3 opensearch-teleport-proxy.py --list` |
| Show cluster details | `python3 opensearch-teleport-proxy.py <name> --show` |
| Start single proxy | `python3 opensearch-teleport-proxy.py <name>` |
| Start all proxies | `python3 opensearch-teleport-proxy.py --all` |
| Teleport login | `tsh app login <app-name>` |
| Check Teleport status | `tsh status` |
| List Teleport apps | `tsh app ls` |
| Find process on port | `lsof -ti:<port>` |
| Kill process on port | `lsof -ti:<port> \| xargs kill` |

---

## Support

### Configuration Files
- **MCP Server:** `~/.mcp.json`
- **MCP Clusters:** `~/.opensearch-mcp-clusters.yml`
- **Proxy Config:** `~/.opensearch-teleport-proxy.json`

### Log Locations
- **Proxy logs:** Stdout (console where proxy is running)
- **MCP server logs:** Check Claude Code logs
- **Teleport logs:** `~/.tsh/`

### Common Issues
1. Certificates not found → `tsh app login <app-name>`
2. Port in use → Kill process or use different port
3. Connection timeout → Re-login to Teleport
4. MCP not connecting → Verify proxy is running and config paths are correct

---

## Notes

- Proxies run in the foreground - keep terminal open or use a terminal multiplexer
- Each cluster requires a separate `tsh app login` command
- Certificates expire - re-login if you see auth errors
- The `opensearch_no_auth: true` setting is correct - authentication is handled by the proxy with Teleport certificates

---

*Last updated: 2025-02-24*
