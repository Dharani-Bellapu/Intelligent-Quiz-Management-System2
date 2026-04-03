import requests
import json
import time
from django.conf import settings


def generate_questions(
    category, subcategory, difficulty, num_questions,
    max_retries=2, model="gemini-2.5-flash", model_options=None
):
    """
    Generate quiz questions using Gemini API.
    Includes:
    - Retry logic
    - Automatic JSON cleanup
    - Validation
    - DB fallback
    """

    import requests, json, time
    from django.conf import settings
    from quizzes.models import AIQuestion

    # Valid models list
    if model_options is None:
        model_options = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-2.5-pro",
        ]

    # Validate selected model
    if model not in model_options:
        model = "gemini-2.5-flash"

    # Prompt
    prompt = (
        f"Generate {num_questions} high-quality multiple-choice questions "
        f"for topic '{subcategory}' under category '{category}' "
        f"at {difficulty.title()} level.\n"
        "RETURN ONLY pure JSON array:\n"
        '[{"question": "...", "options": ["A","B","C","D"], "answer": "A"}]'
    )

    # API request config
    headers = {"Content-Type": "application/json"}
    params = {"key": settings.GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    base_url = "https://generativelanguage.googleapis.com/v1beta/models/"
    endpoint = f"{base_url}{model}:generateContent"

    # -------------- AI Attempts --------------
    for attempt in range(max_retries):
        try:
            print(f"\n=== Attempt {attempt+1}/{max_retries} using model: {model} ===")

            response = requests.post(
                endpoint,
                headers=headers,
                params=params,
                data=json.dumps(payload),
                timeout=45,
            )

            print(f"Status: {response.status_code}")
            print("Preview:", response.text[:300], "...\n")

            response.raise_for_status()

            content = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

            # -------------- Clean Markdown Blocks --------------
            if content.startswith("```json"):
                content = content.replace("```json", "", 1).strip()

            if content.startswith("```"):
                content = content.replace("```", "", 1).strip()

            if content.endswith("```"):
                content = content[:-3].strip()

            # -------------- Parse JSON --------------
            try:
                questions = json.loads(content)
            except Exception:
                print("❌ JSON Decode failed — cleaning response...")
                content = content.replace("\n", "").replace("\t", "").strip()
                questions = json.loads(content)

            # -------------- Validation --------------
            validated = []
            for idx, q in enumerate(questions, 1):
                if not all(k in q for k in ["question", "options", "answer"]):
                    print(f"✗ Question {idx}: Missing keys")
                    continue

                if not isinstance(q["options"], list) or len(q["options"]) != 4:
                    print(f"✗ Question {idx}: Options must be 4")
                    continue

                if q["answer"] not in q["options"]:
                    print(f"✗ Question {idx}: Answer not in options")
                    continue

                validated.append(q)
                print(f"✓ Question {idx}: Valid")

            if validated:
                print(f"✅ AI Success — {len(validated)} validated questions")
                return validated

        except Exception as e:
            print(f"❌ Error: {e}")

    # -------------- Database Fallback --------------
    print("\n🔄 AI failed — trying database fallback...")

    try:
        existing = AIQuestion.objects.filter(
            category=category,
            subcategory=subcategory,
            difficulty=difficulty,
        ).order_by("-created_at")[:num_questions]

        if existing.exists():
            print(f"✅ Using {existing.count()} questions from DB")
            return [
                {"question": q.question_text, "options": q.options, "answer": q.answer}
                for q in existing
            ]
        else:
            print("❌ No fallback questions available")
            return []

    except Exception as e:
        print("❌ DB Error:", e)
        return []



def generate_explanation(question_text, correct_answer, user_answer):
    """
    Generate AI explanation for incorrect answers with better error handling.
    """
    try:
        import google.generativeai as genai
        
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            print("⚠️ GEMINI_API_KEY not configured")
            return f"The correct answer is: {correct_answer}"
        
        genai.configure(api_key=api_key)
        
        prompt = f"""
        Question: {question_text}
        
        Correct Answer: {correct_answer}
        User's Answer: {user_answer}
        
        Provide a brief explanation (2-3 sentences) why the correct answer is "{correct_answer}" 
        and what was wrong with "{user_answer}". Be educational and concise.
        """
        
        print(f"📚 Generating explanation for: {question_text[:50]}...")
        
        model = genai.GenerativeModel("gemini-pro")
        # ✅ REMOVED timeout parameter - Gemini API doesn't support it
        response = model.generate_content(prompt)
        
        if response and response.text:
            result = response.text.strip()
            print(f"✅ Explanation generated: {result[:100]}...")
            return result
        else:
            print("⚠️ Empty response from Gemini API")
            return f"The correct answer is: {correct_answer}"
        
    except ImportError as e:
        print(f"⚠️ google-generativeai not installed: {e}")
        return f"The correct answer is: {correct_answer}"
        
    except Exception as e:
        print(f"❌ Error generating explanation: {type(e).__name__} – {str(e)[:100]}")
        return f"The correct answer is: {correct_answer}"




def parse_ai_response_safely(response_text):
    """
    Safely parse AI response that might contain markdown formatting.
    """
    try:
        # Remove markdown code blocks
        if response_text.startswith("```json"):
            response_text = response_text[len("```json"):].strip()
        elif response_text.startswith("```"):
            response_text = response_text[len("```"):].strip()

        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()

        return json.loads(response_text)

    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON: {e}")
        return []
