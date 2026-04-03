import google.generativeai as genai
from django.conf import settings


def call_ai_explanation_api(question_text, correct_answer, user_answer):
    """Generate AI explanation using Gemini API"""
    try:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return f"The correct answer is: {correct_answer}"
        
        genai.configure(api_key=api_key)
        
        prompt = f"""Question: {question_text}
User's Answer: {user_answer}
Correct Answer: {correct_answer}

Explain why the correct answer is correct and what was wrong with the user's answer (3-4 sentences)."""
        
        print(f"📚 Generating explanation...")
        
        # ✅ USE AVAILABLE MODELS ONLY (from your rate limits dashboard)
        model_options = [
            "gemini-2.5-flash",      # ✅ Available - 250K TPM
            "gemini-2.0-flash",      # ✅ Available - 1M TPM
            "gemini-2.5-flash-lite", # ✅ Available - 250K TPM
            "gemini-2.0-flash-lite", # ✅ Available - 1M TPM
            "gemini-2.5-pro",        # ✅ Available - 125K TPM
        ]
        
        for model_name in model_options:
            try:
                print(f"  Trying model: {model_name}...")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                
                if response and response.text:
                    explanation = response.text.strip()
                    print(f"✅ Explanation generated with {model_name}")
                    return explanation
                    
            except Exception as e:
                error_msg = str(e)[:80]
                print(f"  ⚠️ {model_name} failed: {error_msg}")
                continue
        
        # If all models fail, return fallback
        print("⚠️ All models failed - returning fallback")
        return f"The correct answer is: {correct_answer}\n\nYour answer was: {user_answer}"
        
    except ImportError:
        print("⚠️ google-generativeai library not installed")
        return f"The correct answer is: {correct_answer}"
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__} – {str(e)[:100]}")
        return f"The correct answer is: {correct_answer}"
