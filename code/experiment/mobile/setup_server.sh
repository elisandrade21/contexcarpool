#!/usr/bin/env bash
# Installs the ranking service with HTTPS on a small Ubuntu 24.04 VM (tested on a GCP e2-micro, 1 GB).
# Copy the code/ folder to ~/app/code first (with .tools/apache-jena-4.10.0). Usage: bash setup_server.sh <public IP>
# HTTPS uses a free certificate for <ip>.sslip.io, issued by Caddy.
set -euo pipefail
IP="$1"; HOST="${IP//./-}.sslip.io"
if [ ! -f /swapfile ]; then sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile; fi
sudo apt-get update -y -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q openjdk-17-jdk-headless caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$HOST {
    encode {
        gzip
        match {
            header Content-Type application/wasm*
            header Content-Type text/*
            header Content-Type application/json*
        }
    }
    reverse_proxy 127.0.0.1:8765
}
CADDY
sudo systemctl restart caddy
sudo tee /etc/systemd/system/rankservice.service >/dev/null <<UNIT
[Unit]
Description=ContexCarpool ranking service
After=network.target
[Service]
User=$USER
WorkingDirectory=$HOME/app/code
ExecStart=/usr/bin/java -Xmx400m -cp .tools/apache-jena-4.10.0/lib/* experiment/service/RankService.java 8765 127.0.0.1
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now rankservice
echo "https://$HOST"
