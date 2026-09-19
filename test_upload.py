import requests

def test_upload():
    try:
        res = requests.post("http://127.0.0.1:8000/api/jobs", files={"file": ("test.txt", b"hello world")})
        print(f"Status: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Error: {e}")

test_upload()
