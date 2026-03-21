#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/env"
PYTHON_BIN="python3.12"

echo "==> PyChess setup starting..."
echo "Project directory: $PROJECT_DIR"

# --------------------------------------------------
# Helpers
# --------------------------------------------------
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

print_step() {
  echo
  echo "==> $1"
}

# --------------------------------------------------
# Homebrew
# --------------------------------------------------
print_step "Checking Homebrew"

if ! command_exists brew; then
  echo "Homebrew not found. Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Typical Homebrew shell setup paths
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
else
  echo "Homebrew already installed."
fi

# --------------------------------------------------
# Python 3.12
# --------------------------------------------------
print_step "Checking Python 3.12"

if ! command_exists "$PYTHON_BIN"; then
  echo "Installing Python 3.12..."
  brew install python@3.12
else
  echo "Python 3.12 already installed."
fi

# Make sure shell can find it
if ! command_exists "$PYTHON_BIN"; then
  if [[ -x /opt/homebrew/bin/python3.12 ]]; then
    export PATH="/opt/homebrew/bin:$PATH"
  elif [[ -x /usr/local/bin/python3.12 ]]; then
    export PATH="/usr/local/bin:$PATH"
  fi
fi

if ! command_exists "$PYTHON_BIN"; then
  echo "ERROR: python3.12 still not found after installation."
  exit 1
fi

"$PYTHON_BIN" --version

# --------------------------------------------------
# Stockfish
# --------------------------------------------------
print_step "Checking Stockfish"

if ! command_exists stockfish; then
  echo "Installing Stockfish..."
  brew install stockfish
else
  echo "Stockfish already installed."
fi

if ! command_exists stockfish; then
  if [[ -x /opt/homebrew/bin/stockfish ]]; then
    export PATH="/opt/homebrew/bin:$PATH"
  elif [[ -x /usr/local/bin/stockfish ]]; then
    export PATH="/usr/local/bin:$PATH"
  fi
fi

if ! command_exists stockfish; then
  echo "ERROR: stockfish still not found after installation."
  exit 1
fi

echo "Stockfish path: $(command -v stockfish)"

# --------------------------------------------------
# venv
# --------------------------------------------------
print_step "Creating virtual environment"

if [[ -d "$VENV_DIR" ]]; then
  echo "venv already exists at $VENV_DIR"
else
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  echo "venv created at $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

print_step "Upgrading pip"
python -m pip install --upgrade pip setuptools wheel

# --------------------------------------------------
# Python dependencies
# --------------------------------------------------
print_step "Installing Python dependencies"

if [[ -f "$PROJECT_DIR/requirements.txt" ]]; then
  echo "requirements.txt found. Installing from requirements.txt ..."
  pip install -r "$PROJECT_DIR/requirements.txt"
else
  echo "No requirements.txt found. Installing core dependencies directly..."
  pip install PySide6 python-chess
fi

# --------------------------------------------------
# Final checks
# --------------------------------------------------
print_step "Running final checks"

python - <<'PY'
import importlib
mods = ["PySide6", "chess"]
for mod in mods:
    importlib.import_module(mod)
print("Python package check passed: PySide6, python-chess")
PY

echo "Python executable: $(which python)"
echo "Pip executable: $(which pip)"
echo "Stockfish executable: $(command -v stockfish)"

print_step "Setup completed successfully"
echo "Activate the environment with:"
echo "  source env/bin/activate"
echo
echo "Then run:"
echo "  python server.py"
echo "  python main_client.py"