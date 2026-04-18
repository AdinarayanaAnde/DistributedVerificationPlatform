#!/usr/bin/env python3
"""Quick test to verify server-side report generation."""

import urllib.request
import json
import time
import sys

BASE_URL = "http://localhost:8000/api"

def register_client():
    """Register a test client."""
    print("📝 Registering client...")
    data = json.dumps({"name": "Test Client - Report Gen"}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/clients/register",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    response = urllib.request.urlopen(req)
    client = json.loads(response.read().decode())
    print(f"✓ Client registered: {client['client_key'][:12]}...")
    return client["client_key"]

def create_run(client_key):
    """Create a test run."""
    print("🚀 Starting test run...")
    data = json.dumps({
        "client_key": client_key,
        "selected_tests": [
            "tests/test_api_quick.py::test_api_health_check",
            "tests/test_data_quick.py::test_db_connection"
        ],
        "resource_name": "default-resource"
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/runs",
        data=data,
        headers={"Content-Type": "application/json"},
    )
