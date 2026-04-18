#!/usr/bin/env python3
import urllib.request
import json

try:
    print("Testing backend API...")
    response = urllib.request.urlopen('http://localhost:8000/api/tests/discover')
    data = json.loads(response.read().decode())
    
    print(f"\n✓ Backend is working!")
    print(f"✓ Tests discovered: {len(data)}")
    
    if data:
        print("\nFirst 5 tests:")
        for t in data[:5]:
            print(f"  • {t['nodeid']}")
    else:
        print("\n✗ No tests found!")
        
except Exception as e:
    print(f"\n✗ ERROR: {e}")
