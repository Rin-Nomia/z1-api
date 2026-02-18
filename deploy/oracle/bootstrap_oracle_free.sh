#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Rin-Nomia/continuum-api.git}"
REPO_DIR="${REPO_DIR:-/opt/continuum-api}"
REPO_BRANCH="${REPO_BRANCH:-main}"
RUN_USER="${RUN_USER:-${SUDO_USER:-ubuntu}}"

echo "[1/6] Installing base packages..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg git apache2-utils

echo "[2/6] Installing Docker Engine + Compose plugin..."
if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
  fi
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    ${VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

sudo usermod -aG docker "$RUN_USER" || true

echo "[3/6] Preparing repository at ${REPO_DIR}..."
if [ ! -d "${REPO_DIR}/.git" ]; then
  sudo mkdir -p "$(dirname "${REPO_DIR}")"
  sudo git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${REPO_DIR}"
else
  sudo git -C "${REPO_DIR}" fetch origin "${REPO_BRANCH}"
  sudo git -C "${REPO_DIR}" checkout "${REPO_BRANCH}"
  sudo git -C "${REPO_DIR}" pull origin "${REPO_BRANCH}"
fi

sudo chown -R "${RUN_USER}:${RUN_USER}" "${REPO_DIR}"

echo "[4/6] Preparing environment files..."
cd "${REPO_DIR}"
if [ ! -f ".env" ]; then
  cp "deploy/oracle/.env.oracle.example" ".env"
  echo "Created ${REPO_DIR}/.env from template."
fi
mkdir -p data/license data/logs
if [ ! -f "data/license/license.enc" ]; then
  echo "{}" > data/license/license.enc
fi

echo "[5/6] Opening firewall ports (80/443/7860)..."
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 80/tcp || true
  sudo ufw allow 443/tcp || true
  sudo ufw allow 7860/tcp || true
fi

echo "[6/6] Bootstrap done."
echo
echo "Next actions:"
echo "  1) Edit ${REPO_DIR}/.env with real secrets and domains"
echo "  2) Put encrypted license at ${REPO_DIR}/data/license/license.enc"
echo "  3) Run: cd ${REPO_DIR} && ./deploy/oracle/up_oracle_stack.sh"
echo
echo "Hash helpers:"
echo "  - C3 admin hash: python3 generate_c3_password_hash.py"
echo "  - Basic auth hash: docker run --rm caddy:2.9.1-alpine caddy hash-password --plaintext 'YourStrongPass!'"
