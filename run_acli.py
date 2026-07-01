import socket
import sys

# Monkeypatch socket.getaddrinfo to force IPv4 (avoiding IPv6 WinError 10051)
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4_only

# Run the agents-cli main entrypoint
try:
    from google.agents.cli.main import main
except ImportError as e:
    print("Error: google-agents-cli is not installed in the active environment.")
    sys.exit(1)

if __name__ == '__main__':
    sys.exit(main())
