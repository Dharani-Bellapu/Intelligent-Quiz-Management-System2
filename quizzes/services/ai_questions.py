import requests
import json
import time
from django.conf import settings


def generate_questions(category, subcategory, difficulty, num_questions, max_retries=2):
    """
    Generate quiz questions with retry logic, validation, and database fallback.
    """
    from quizzes.models import AIQuestion  # import inside to avoid circular import

    # ✨ SCENARIO 1: Try AI Generation First
    prompt = (
        f"Generate {num_questions} high quality multiple-choice questions on the topic '{subcategory}' "
        f"under the category '{category}' at {difficulty.title()} level. "
        "Return ONLY a JSON list like: "
        '[{"question": "Q1?", "options": ["A", "B", "C", "D"], "answer": "A"}, ...]'
    )

    headers = {"Content-Type": "application/json"}
    params = {"key": settings.GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )

    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}: Generating {num_questions} questions...")

            response = requests.post(
                endpoint,
                headers=headers,
                params=params,
                data=json.dumps(payload),
                timeout=90,
            )

            print(f"DEBUG: Status {response.status_code}")
            print(f"DEBUG: Response preview: {response.text[:500]}")

            response.raise_for_status()

            content = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

            # --- Clean up markdown wrappers ---
            if content.startswith("```json"):
                content = content[len("```json"):].strip()
            elif content.startswith("```"):
                content = content[len("```"):].strip()

            if content.endswith("```"):
                content = content[:-3].strip()

            # --- Parse JSON ---
            questions = json.loads(content)

            validated = []
            for idx, q in enumerate(questions, 1):
                if all(k in q for k in ["question", "options", "answer"]):
                    if isinstance(q["options"], list) and len(q["options"]) == 4:
                        if q["answer"] in q["options"]:
                            validated.append(q)
                            print(f"✓ Question {idx}: Valid")
                        else:
                            print(f"✗ Question {idx}: Answer '{q['answer']}' not in options")
                    else:
                        print(
                            f"✗ Question {idx}: Invalid options "
                            f"(expected 4, got {len(q.get('options', []))})"
                        )
                else:
                    print(f"✗ Question {idx}: Missing required keys")

            if validated:
                print(f"✅ SCENARIO 1: AI Generation Success — {len(validated)}/{len(questions)} validated")
                return validated
            else:
                print("⚠️ No valid questions generated; retrying if possible.")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                break  # exit loop to try fallback

        except requests.exceptions.Timeout:
            print(f"⏳ Timeout on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                print("Retrying in 3 seconds…")
                time.sleep(3)
            else:
                break

        except json.JSONDecodeError as je:
            print(f"❌ JSON parsing failed on attempt {attempt + 1}: {je}")
            if attempt < max_retries - 1:
                print("Retrying in 2 seconds…")
                time.sleep(2)
            else:
                break

        except Exception as e:
            print(f"❌ Error on attempt {attempt + 1}: {type(e).__name__} – {e}")
            if attempt < max_retries - 1:
                print("Retrying in 2 seconds…")
                time.sleep(2)
            else:
                break

    # ✨ SCENARIO 2: AI Failed — Fallback to Database
    print("\n🔄 AI generation failed. Checking database for existing questions…")

    try:
        existing = (
            AIQuestion.objects.filter(
                category=category,
                subcategory=subcategory,
                difficulty=difficulty,
            )
            .order_by("-created_at")[:num_questions]
        )

        if existing.exists():
            print(f"✅ SCENARIO 2: Fallback Success — {existing.count()} questions found in DB")
            return [
                {"question": q.question_text, "options": q.options, "answer": q.answer}
                for q in existing
            ]

        print(f"❌ No questions found in DB for {category} > {subcategory} ({difficulty})")
        return []

    except Exception as e:
        print(f"❌ Database fallback failed: {e}")
        return []
