#!/usr/bin/env python3
import urllib.request
import sys
import socket


def check_health():
    try:
        # First check if the port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", 8000))
        sock.close()

        if result != 0:
            print("Port 8000 is not open", file=sys.stderr)
            sys.exit(1)

        # Then try to make an HTTP request
        req = urllib.request.Request(
            "http://127.0.0.1:8000/",
            headers={"User-Agent": "Docker-Healthcheck"}
        )

        with urllib.request.urlopen(req, timeout=3) as response:
            status = response.getcode()
            if 200 <= status < 500:  # Accept any non-5xx status
                print(f"Health check passed with status {status}")
                sys.exit(0)
            else:
                print(f"Health check failed with status {status}", file=sys.stderr)
                sys.exit(1)

    except urllib.error.HTTPError as e:
        # Accept redirects and client errors (they mean the app is running)
        if 300 <= e.code < 500:
            print(f"Health check passed with HTTP status {e.code}")
            sys.exit(0)
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Health check failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    check_health()