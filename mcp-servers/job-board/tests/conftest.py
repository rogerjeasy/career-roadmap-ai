"""pytest configuration: add mcp-servers/ to sys.path so `shared` is importable."""
import os
import sys

# mcp-servers/ parent → enables `from shared.xxx import ...`
_MCP_SERVERS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# mcp-servers/job-board/ → enables `from models import ...` etc.
_JOB_BOARD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _path in (_MCP_SERVERS, _JOB_BOARD):
    if _path not in sys.path:
        sys.path.insert(0, _path)
