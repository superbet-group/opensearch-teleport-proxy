#!/usr/bin/env python3
"""
Multi-cluster OpenSearch Teleport Proxy

Local HTTP proxy that forwards requests to HTTPS Teleport OpenSearch apps with client certificates.
Supports multiple clusters configured via JSON file.

Usage:
  # Generate sample config
  python3 opensearch-teleport-proxy.py --init-config

  # List available clusters
  python3 opensearch-teleport-proxy.py --list

  # Show cluster details
  python3 opensearch-teleport-proxy.py trading-topics-qa --show

  # Start proxy for a single cluster
  tsh app login opensearch-trading-topics-qa
  python3 opensearch-teleport-proxy.py trading-topics-qa

  # Start proxies for ALL clusters at once
  python3 opensearch-teleport-proxy.py --all

  # Start with custom port
  python3 opensearch-teleport-proxy.py trading-topics-qa --port 9999

Then set MCP server env: OPENSEARCH_URL=http://127.0.0.1:<port>, OPENSEARCH_NO_AUTH=true
"""
import http.server
import urllib.request
import ssl
import os
import json
import urllib.error
import argparse
import sys
import signal
import multiprocessing
from urllib.parse import urlparse


# Configuration Management Functions

def find_config_file(custom_path=None):
    """Search for config file in standard locations."""
    # Check environment variable first
    env_path = os.environ.get('OPENSEARCH_PROXY_CONFIG')

    search_paths = [
        custom_path,
        env_path,
        os.path.expanduser("~/.opensearch-teleport-proxy.json"),
        os.path.expanduser("~/.config/opensearch-teleport-proxy.json"),
        "/etc/opensearch-teleport-proxy.json",
        "./opensearch-teleport-proxy.json"
    ]

    for path in search_paths:
        if path and os.path.exists(path):
            return path

    raise FileNotFoundError(
        "Configuration file not found.\n"
        "Searched locations:\n"
        "  - ~/.opensearch-teleport-proxy.json\n"
        "  - ~/.config/opensearch-teleport-proxy.json\n"
        "  - /etc/opensearch-teleport-proxy.json\n"
        "  - ./opensearch-teleport-proxy.json\n\n"
        "Generate a sample configuration:\n"
        "  python3 opensearch-teleport-proxy.py --init-config\n\n"
        "Or specify a custom config file:\n"
        "  python3 opensearch-teleport-proxy.py --config /path/to/config.json"
    )


def load_config(config_path):
    """Load and parse JSON config file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}")
    except Exception as e:
        raise ValueError(f"Error reading config file: {e}")


def validate_config(config):
    """Validate config schema."""
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object")

    if 'clusters' not in config:
        raise ValueError("Missing required field: clusters")

    if not isinstance(config['clusters'], dict):
        raise ValueError("'clusters' must be an object")

    if not config['clusters']:
        raise ValueError("No clusters defined in configuration")

    # Validate each cluster
    for name, cluster in config['clusters'].items():
        if not isinstance(cluster, dict):
            raise ValueError(f"Cluster '{name}' must be an object")

        required_fields = ['app_name', 'teleport_url', 'port']
        for field in required_fields:
            if field not in cluster:
                raise ValueError(f"Cluster '{name}' missing required field: {field}")

        # Validate port is integer
        if not isinstance(cluster['port'], int):
            raise ValueError(f"Cluster '{name}' port must be an integer (got {type(cluster['port']).__name__})")

        # Validate URL format
        url = cluster['teleport_url']
        if not url.startswith(('https://', 'http://')):
            raise ValueError(f"Cluster '{name}' teleport_url must start with https:// or http://")


def get_cluster_config(config, cluster_name):
    """Get specific cluster config merged with defaults."""
    if cluster_name not in config['clusters']:
        raise KeyError(f"Cluster '{cluster_name}' not found in configuration")

    # Start with defaults
    defaults = config.get('defaults', {})
    cluster_config = defaults.copy()

    # Merge cluster-specific config (overrides defaults)
    cluster_config.update(config['clusters'][cluster_name])

    # Set default values if not provided
    cluster_config.setdefault('tsh_keys_dir', '~/.tsh/keys/teleport.happening.dev')
    cluster_config.setdefault('listen_host', '127.0.0.1')
    cluster_config.setdefault('timeout', 60)

    # Expand tilde in paths
    cluster_config['tsh_keys_dir'] = os.path.expanduser(cluster_config['tsh_keys_dir'])

    # Apply environment variable overrides
    if os.environ.get('OPENSEARCH_PROXY_PORT'):
        try:
            cluster_config['port'] = int(os.environ['OPENSEARCH_PROXY_PORT'])
        except ValueError:
            pass

    if os.environ.get('OPENSEARCH_PROXY_TSH_KEYS'):
        cluster_config['tsh_keys_dir'] = os.path.expanduser(os.environ['OPENSEARCH_PROXY_TSH_KEYS'])

    if os.environ.get('OPENSEARCH_PROXY_TIMEOUT'):
        try:
            cluster_config['timeout'] = int(os.environ['OPENSEARCH_PROXY_TIMEOUT'])
        except ValueError:
            pass

    if os.environ.get('OPENSEARCH_PROXY_VERBOSE') in ('1', 'true', 'True', 'yes'):
        cluster_config['verbose'] = True

    return cluster_config


# Certificate Discovery Functions

def list_available_certs(tsh_keys_dir):
    """List all .crt files found (without extension)."""
    certs = set()
    try:
        for root, _, files in os.walk(tsh_keys_dir):
            for f in files:
                if f.endswith('.crt'):
                    certs.add(f[:-4])  # Remove .crt extension
    except Exception:
        pass
    return sorted(certs)


def find_certs(app_name, tsh_keys_dir):
    """Find {app_name}.crt and {app_name}.key under tsh_keys_dir."""
    cert_name = f"{app_name}.crt"
    key_name = f"{app_name}.key"

    for root, _, files in os.walk(tsh_keys_dir):
        if cert_name in files and key_name in files:
            return (
                os.path.join(root, cert_name),
                os.path.join(root, key_name),
            )

    # Build helpful error message
    available = list_available_certs(tsh_keys_dir)
    available_str = "\n  - ".join(available) if available else "None found"

    raise FileNotFoundError(
        f"Certificate not found for '{app_name}'\n\n"
        f"Run: tsh app login {app_name}\n\n"
        f"Then ensure {cert_name} and {key_name} exist under:\n"
        f"  {tsh_keys_dir}\n\n"
        f"Available certificates found:\n  - {available_str}\n\n"
        f"Troubleshooting:\n"
        f"  1. Verify you're logged in: tsh status\n"
        f"  2. Login to the app: tsh app login {app_name}\n"
        f"  3. Check certificates: ls -la {tsh_keys_dir}/*/teleport.happening.dev/"
    )


# ProxyHandler Factory Function

def create_proxy_handler(cluster_config):
    """Factory function to create ProxyHandler with cluster-specific config."""
    target_url = cluster_config['teleport_url']
    cert_file = cluster_config['cert_file']
    key_file = cluster_config['key_file']
    timeout = cluster_config.get('timeout', 60)
    verbose = cluster_config.get('verbose', False)
    cluster_name = cluster_config.get('cluster_name', 'unknown')

    class ConfiguredProxyHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._proxy(b"")

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            self._proxy(body)

        def do_PUT(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            self._proxy(body)

        def do_HEAD(self):
            self._proxy(b"")

        def do_DELETE(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            self._proxy(body)

        def _proxy(self, body):
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            qs = parsed.query
            url = target_url + path + ("?" + qs if qs else "")

            req = urllib.request.Request(
                url, data=body if body else None, method=self.command
            )
            for k, v in self.headers.items():
                if k.lower() in ("host", "connection", "transfer-encoding"):
                    continue
                req.add_header(k, v)
            req.add_header("Host", urlparse(target_url).netloc)

            ctx = ssl.create_default_context()
            ctx.load_cert_chain(cert_file, key_file)
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("transfer-encoding", "connection"):
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(resp.read())
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.end_headers()
                self.wfile.write(e.read())
            except Exception as e:
                if verbose:
                    print(f"[{cluster_name}] ERROR: {e}", file=sys.stderr)
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        def log_message(self, format, *args):
            if verbose:
                print(f"[{cluster_name}] {args[0]}")

    return ConfiguredProxyHandler


# CLI Utility Functions

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="OpenSearch Teleport Proxy - Multi-cluster support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate sample config
  python3 opensearch-teleport-proxy.py --init-config

  # List all clusters
  python3 opensearch-teleport-proxy.py --list

  # Show cluster details
  python3 opensearch-teleport-proxy.py trading-topics-qa --show

  # Start proxy for a single cluster
  python3 opensearch-teleport-proxy.py trading-topics-qa

  # Start proxies for ALL clusters
  python3 opensearch-teleport-proxy.py --all

  # Start with custom port
  python3 opensearch-teleport-proxy.py trading-topics-qa --port 9999
"""
    )
    parser.add_argument('cluster', nargs='?', help='Cluster name from config')
    parser.add_argument('--list', '-l', action='store_true', help='List all clusters')
    parser.add_argument('--show', '-s', action='store_true', help='Show cluster config')
    parser.add_argument('--all', '-a', action='store_true', help='Start proxies for all clusters')
    parser.add_argument('--config', '-c', help='Config file path')
    parser.add_argument('--port', '-p', type=int, help='Override listen port')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--init-config', action='store_true', help='Generate sample config')
    parser.add_argument('--version', action='version', version='1.0.0')
    return parser.parse_args()


def list_clusters(config):
    """Print all available clusters."""
    print("\nAvailable clusters:")
    for name, cluster in config.get('clusters', {}).items():
        desc = cluster.get('description', 'No description')
        port = cluster.get('port', 'N/A')
        print(f"  - {name} (port {port}): {desc}")
    print()


def show_cluster(config, cluster_name):
    """Print detailed cluster configuration."""
    if cluster_name not in config['clusters']:
        print(f"ERROR: Cluster '{cluster_name}' not found")
        list_clusters(config)
        sys.exit(1)

    merged = get_cluster_config(config, cluster_name)
    print(f"\nCluster: {cluster_name}")
    print(f"  App Name: {merged['app_name']}")
    print(f"  Teleport URL: {merged['teleport_url']}")
    print(f"  Port: {merged['port']}")
    print(f"  TSH Keys: {merged['tsh_keys_dir']}")
    print(f"  Timeout: {merged.get('timeout', 60)}s")
    print(f"  Listen Host: {merged.get('listen_host', '127.0.0.1')}")
    print(f"  Description: {merged.get('description', 'N/A')}")
    print()


def init_config_file():
    """Generate sample configuration file."""
    sample_config = {
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

    config_path = os.path.expanduser("~/.opensearch-teleport-proxy.json")

    # Check if file already exists
    if os.path.exists(config_path):
        print(f"Configuration file already exists at: {config_path}")
        response = input("Overwrite? [y/N]: ")
        if response.lower() not in ('y', 'yes'):
            print("Aborted.")
            return

    try:
        with open(config_path, 'w') as f:
            json.dump(sample_config, f, indent=2)
        print(f"\nCreated sample config at: {config_path}")
        print("\nNext steps:")
        print("  1. Edit the config file to add your clusters")
        print(f"     vi {config_path}")
        print("  2. List available clusters")
        print("     python3 opensearch-teleport-proxy.py --list")
        print("  3. Start proxy for a cluster")
        print("     python3 opensearch-teleport-proxy.py <cluster-name>")
    except Exception as e:
        print(f"ERROR: Failed to create config file: {e}")
        sys.exit(1)


# Multi-cluster Management Functions

def start_cluster_proxy(cluster_name, cluster_config, verbose=False):
    """Start a proxy for a single cluster (runs in subprocess)."""
    cluster_config['cluster_name'] = cluster_name
    if verbose:
        cluster_config['verbose'] = True

    # Find certificates
    try:
        cert_file, key_file = find_certs(
            cluster_config['app_name'],
            cluster_config['tsh_keys_dir']
        )
        cluster_config['cert_file'] = cert_file
        cluster_config['key_file'] = key_file
    except FileNotFoundError as e:
        print(f"[{cluster_name}] ERROR: {e}")
        return

    # Create and start proxy server
    handler_class = create_proxy_handler(cluster_config)
    listen_host = cluster_config.get('listen_host', '127.0.0.1')
    listen_port = cluster_config['port']

    try:
        server = http.server.HTTPServer((listen_host, listen_port), handler_class)
    except OSError as e:
        if 'Address already in use' in str(e) or 'address already in use' in str(e).lower():
            print(f"[{cluster_name}] ERROR: Port {listen_port} already in use")
            return
        raise

    print(f"[{cluster_name}] Proxying http://{listen_host}:{listen_port} -> {cluster_config['teleport_url']}")
    print(f"[{cluster_name}] Client cert: {cert_file}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{cluster_name}] Proxy stopped")


def start_all_clusters(config, verbose=False):
    """Start proxies for all configured clusters."""
    clusters = config.get('clusters', {})

    if not clusters:
        print("ERROR: No clusters defined in configuration")
        return

    print(f"\nStarting proxies for {len(clusters)} cluster(s)...\n")

    # Create a process for each cluster
    processes = []
    for cluster_name in clusters.keys():
        try:
            cluster_config = get_cluster_config(config, cluster_name)

            # Create process
            process = multiprocessing.Process(
                target=start_cluster_proxy,
                args=(cluster_name, cluster_config, verbose),
                name=f"proxy-{cluster_name}"
            )
            process.start()
            processes.append((cluster_name, process))

        except Exception as e:
            print(f"[{cluster_name}] ERROR: Failed to start proxy: {e}")

    if not processes:
        print("ERROR: No proxies started")
        return

    print(f"\n{len(processes)} proxy/proxies started successfully!")
    print("\nSet MCP server environment for each cluster:")
    for cluster_name in clusters.keys():
        cluster_config = get_cluster_config(config, cluster_name)
        port = cluster_config['port']
        listen_host = cluster_config.get('listen_host', '127.0.0.1')
        print(f"  [{cluster_name}] OPENSEARCH_URL=http://{listen_host}:{port} OPENSEARCH_NO_AUTH=true")

    print("\nPress Ctrl+C to stop all proxies\n")

    # Wait for all processes
    try:
        for cluster_name, process in processes:
            process.join()
    except KeyboardInterrupt:
        print("\n\nStopping all proxies...")
        for cluster_name, process in processes:
            print(f"  Stopping [{cluster_name}]...")
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
        print("All proxies stopped")


# Main Function

def main():
    args = parse_arguments()

    # Handle init-config command (no config file needed)
    if args.init_config:
        init_config_file()
        return

    # Load configuration
    try:
        config_path = find_config_file(args.config)
        config = load_config(config_path)
        validate_config(config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Invalid configuration: {e}")
        sys.exit(1)

    # Handle list command
    if args.list:
        list_clusters(config)
        return

    # Handle all command
    if args.all:
        start_all_clusters(config, verbose=args.verbose)
        return

    # Require cluster name for other operations
    if not args.cluster:
        print("ERROR: Cluster name required\n")
        list_clusters(config)
        print("Usage: python3 opensearch-teleport-proxy.py <cluster-name>")
        print("       python3 opensearch-teleport-proxy.py --list")
        print("       python3 opensearch-teleport-proxy.py --all")
        print("       python3 opensearch-teleport-proxy.py --init-config")
        sys.exit(1)

    # Handle show command
    if args.show:
        show_cluster(config, args.cluster)
        return

    # Get cluster configuration
    try:
        cluster_config = get_cluster_config(config, args.cluster)
    except KeyError:
        print(f"ERROR: Cluster '{args.cluster}' not found in configuration\n")
        list_clusters(config)
        sys.exit(1)

    # Apply CLI overrides
    if args.port:
        cluster_config['port'] = args.port
    if args.verbose:
        cluster_config['verbose'] = True

    cluster_config['cluster_name'] = args.cluster

    # Find certificates
    try:
        cert_file, key_file = find_certs(
            cluster_config['app_name'],
            cluster_config['tsh_keys_dir']
        )
        cluster_config['cert_file'] = cert_file
        cluster_config['key_file'] = key_file
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Create and start proxy server
    handler_class = create_proxy_handler(cluster_config)
    listen_host = cluster_config.get('listen_host', '127.0.0.1')
    listen_port = cluster_config['port']

    try:
        server = http.server.HTTPServer((listen_host, listen_port), handler_class)
    except OSError as e:
        if 'Address already in use' in str(e) or 'address already in use' in str(e).lower():
            print(f"ERROR: Cannot bind to {listen_host}:{listen_port} - port already in use\n")
            print("This usually means another proxy is running on this port.")
            print("Try one of these solutions:\n")
            print(f"  1. Stop the other process using port {listen_port}:")
            print(f"     lsof -ti:{listen_port} | xargs kill\n")
            print(f"  2. Use a different port:")
            print(f"     python3 opensearch-teleport-proxy.py {args.cluster} --port 9999\n")
            print(f"  3. Update the config file to use a different port for this cluster")
            sys.exit(1)
        raise

    print(f"[{args.cluster}] Proxying http://{listen_host}:{listen_port} -> {cluster_config['teleport_url']}")
    print(f"[{args.cluster}] Client cert: {cert_file}")
    print(f"\nSet MCP server environment:")
    print(f"  OPENSEARCH_URL=http://{listen_host}:{listen_port}")
    print(f"  OPENSEARCH_NO_AUTH=true")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{args.cluster}] Proxy stopped")


if __name__ == "__main__":
    main()
