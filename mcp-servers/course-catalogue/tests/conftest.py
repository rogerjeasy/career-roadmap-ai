"""pytest configuration: add mcp-servers/ to sys.path so `shared` is importable."""
import os
import sys

# mcp-servers/ parent → enables `from shared.xxx import ...`
_MCP_SERVERS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# mcp-servers/course-catalogue/ → enables `from models import ...` etc.
_COURSE_CATALOGUE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _path in (_MCP_SERVERS, _COURSE_CATALOGUE):
    if _path not in sys.path:
        sys.path.insert(0, _path)
