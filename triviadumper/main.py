import json
from pathlib import Path

import httpx

SUPABASE_URL = "https://nnlkcwvqhkxasjtshvpw.supabase.co"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5ubGtjd3ZxaGt4YXNqdHNodnB3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUxODY4MzAsImV4cCI6MjA4MDc2MjgzMH0.BtEWYzE4ZA6Fc8rr0n28fPhvIcWdwzoBaOMbAqHYoAo"

HEADERS = {
    "apikey": API_KEY,
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

OUTPUT_FILE = Path("questions.json")

START_ID = 1
MAX_CONSECUTIVE_MISSES = 20

questions = []
misses = 0
question_id = START_ID

with httpx.Client(timeout=10) as client:
    while misses < MAX_CONSECUTIVE_MISSES:
        r = client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/get_question_by_id",
            headers=HEADERS,
            json={"input_id": question_id},
        )

        if r.is_success:
            data = r.json()

            if data:
                questions.extend(data)
                print(f"✓ {question_id}")
                misses = 0
            else:
                print(f"- missing {question_id}")
                misses += 1
        else:
            print(f"! error {question_id}: {r.status_code} {r.text}")
            misses += 1

        question_id += 1

questions.sort(key=lambda x: x["id"])

OUTPUT_FILE.write_text(
    json.dumps(questions, indent=4, ensure_ascii=False), encoding="utf-8"
)

print(f"\nSaved {len(questions)} questions → {OUTPUT_FILE}")
