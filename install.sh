#!/bin/bash
# C3 — Claude Code Companion Installer
# Installs c3 as a globally available command

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get version from cli/c3.py
C3_VER=$(grep "__version__ =" "$SCRIPT_DIR/cli/c3.py" | cut -d'"' -f2)

echo "╔══════════════════════════════════════════════╗"
echo "║   C3 — Claude Code Companion Installer       ║"
echo "║   Version: v$C3_VER                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Please install it first."
    exit 1
fi

echo "📦 Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" --break-system-packages -q 2>/dev/null || \
pip3 install -r "$SCRIPT_DIR/requirements.txt" -q

# Create wrapper script
echo "🔗 Creating c3 command..."

WRAPPER="/usr/local/bin/c3"
if [ ! -w "/usr/local/bin" ]; then
    WRAPPER="$HOME/.local/bin/c3"
    mkdir -p "$HOME/.local/bin"
fi

cat > "$WRAPPER" << EOF
#!/bin/bash
PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/cli/c3.py" "\$@"
EOF

chmod +x "$WRAPPER"

echo ""
echo "✅ C3 installed successfully!"
echo ""
echo "Quick start:"
echo "  cd /your/project"
echo "  c3 init ."
echo "  c3 init . --force                  # Existing C3 project: apply latest migrations"
echo "  c3 install-mcp .                   # Register MCP tools for your IDE (auto-detect)"
echo "  c3 ui                              # Launch web dashboard"
echo "  c3 stats                           # CLI stats"
echo "  c3 context 'fix the auth bug'      # Get context"
echo "  c3 pipe 'fix the auth bug'            # All-in-one context pipeline"
echo ""
echo "Run 'c3 --help' for all commands."

