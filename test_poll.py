import requests
import time

job_id = "5a8a25cc-3bba-49a0-b6fd-248d53d62f36"
for i in range(10):
    res = requests.get(f"http://127.0.0.1:8000/api/jobs/{job_id}")
    data = res.json()
    print(f"Status: {data['status']}, Error: {data['error_message']}")
    if data['status'] in ['COMPLETED', 'FAILED']:
        break
    time.sleep(1)
