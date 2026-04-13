import requests
import json

def test_api():
    print("🧪 Testing Distributed Verification Platform API")
    print("=" * 50)

    # Test health endpoint
    print("1. Testing health endpoint...")
    try:
        response = requests.get('http://localhost:8000/health')
        print(f"   ✅ Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")

    # Test test discovery
    print("\n2. Testing test discovery...")
    try:
        response = requests.get('http://localhost:8000/api/tests/discover')
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('content-type', 'unknown')}")
        if response.status_code == 200:
            tests = response.json()
            print(f"   ✅ Found {len(tests)} tests")
            for test in tests[:3]:  # Show first 3
                print(f"      - {test['nodeid']}")
        else:
            print(f"   ❌ Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   ❌ Test discovery failed: {e}")

    # Test metrics endpoint
    print("\n3. Testing metrics endpoint...")
    try:
        response = requests.get('http://localhost:8000/api/metrics')
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            metrics = response.json()
            print("   ✅ Metrics retrieved:")
            print(f"      - Total runs: {metrics['total_runs']}")
            print(f"      - Success rate: {metrics['success_rate']}%")
            print(f"      - Running: {metrics['running_runs']}")
        else:
            print(f"   ❌ Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   ❌ Metrics failed: {e}")

    # Test client registration
    print("\n4. Testing client registration...")
    try:
        response = requests.post('http://localhost:8000/api/clients/register',
                               json={"name": "TestClient", "email": "test@example.com", "webhook_url": "http://example.com/webhook"})
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            client = response.json()
            print(f"   ✅ Client registered: {client['name']} (key: {client['client_key'][:10]}...)")
            client_key = client['client_key']
        else:
            print(f"   ❌ Response: {response.text[:200]}...")
            client_key = None
    except Exception as e:
        print(f"   ❌ Client registration failed: {e}")
        client_key = None

    # Test run creation (if client was created)
    if client_key:
        print("\n5. Testing run creation...")
        try:
            response = requests.post('http://localhost:8000/api/runs',
                                   json={"client_key": client_key, "selected_tests": ["test_example.py::test_basic"]})
            run = response.json()
            print(f"   ✅ Run created: ID {run['id']}, Status: {run['status']}")
        except Exception as e:
            print(f"   ❌ Run creation failed: {e}")

    print("\n🎉 API testing complete!")
    print("\n📱 Now test the frontend at: http://localhost:5173")

if __name__ == "__main__":
    test_api()