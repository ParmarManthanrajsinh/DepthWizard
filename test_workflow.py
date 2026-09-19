import requests
import time
import json

def test_workflow():
    try:
        # Invalid file upload
        res = requests.post("http://127.0.0.1:8000/api/jobs", files={"file": ("test.txt", b"not an image")})
        data = res.json()
        job_id = data["id"]
        
        # Poll
        for _ in range(10):
            res2 = requests.get(f"http://127.0.0.1:8000/api/jobs/{job_id}")
            d2 = res2.json()
            if d2["status"] in ["COMPLETED", "FAILED"]:
                print(f"Final Status: {d2['status']}")
                print(f"Error: {d2['error_message']}")
                break
            time.sleep(1)
    except Exception as e:
        print(f"Error: {e}")

test_workflow()
