from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from .models import Category, Subcategory, AIQuestion, UserQuizAttempt, UserAnswer
from .services.ai_questions import generate_questions
from quizzes.ai_utils import call_ai_explanation_api
from quizzes.models import UserActivity
import json
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils.safestring import mark_safe
from django.db.models import Q


@login_required
def subcategory_selection(request, category_id):
    """
    Select subcategory, difficulty, and number of questions
    
    Args:
        request: HTTP request
        category_id: ID of the selected category
    """
    category = get_object_or_404(Category, pk=category_id)
    subcategories = category.subcategories.all()

    if request.method == "POST":
        subcategory_id = request.POST.get("subcategory")
        difficulty = request.POST.get("difficulty", "").capitalize()
        num_questions = request.POST.get("num_questions")

        if subcategory_id and difficulty and num_questions:
            try:
                subcat = get_object_or_404(Subcategory, pk=subcategory_id)
                num_questions = int(num_questions)

                # Validate num_questions range
                if num_questions < 1 or num_questions > 50:
                    raise ValueError("Number of questions must be between 1 and 50")

                # Generate questions using AI service
                print(f"🎯 Generating {num_questions} {difficulty} questions for {subcat.name}...")
                questions = generate_questions(
                    category.name,
                    subcat.name,
                    difficulty,
                    num_questions,
                )

                if not questions:
                    raise Exception("Failed to generate questions. Please try again.")

                # Cache questions in database
                created_count = 0
                for q in questions:
                    AIQuestion.objects.create(
                        category=category.name,
                        subcategory=subcat.name,
                        difficulty=difficulty,
                        question_text=q["question"],
                        options=q["options"],
                        answer=q["answer"],
                    )
                    created_count += 1

                print(f"✅ {created_count} questions created successfully")

                # Store quiz metadata in session
                request.session['ai_category'] = category.name
                request.session['ai_subcategory'] = subcat.name
                request.session['ai_difficulty'] = difficulty
                request.session['ai_num_questions'] = num_questions

                return redirect('quiz_start')

            except ValueError as ve:
                error = str(ve)
            except Exception as e:
                error = f"Error: {str(e)}"
                print(f"❌ Exception in subcategory_selection: {e}")
        else:
            error = "Please select all options."

        return render(request, "quizzes/subcategory_selection.html", {
            "category": category,
            "subcategories": subcategories,
            "error": error,
        })

    return render(request, "quizzes/subcategory_selection.html", {
        "category": category,
        "subcategories": subcategories,
    })


@login_required
def quiz_start(request):
    """
    Start quiz - load questions and create attempt
    """
    category = request.session.get('ai_category')
    subcategory = request.session.get('ai_subcategory')
    difficulty = request.session.get('ai_difficulty')
    num_questions = request.session.get('ai_num_questions')

    if not (category and subcategory and difficulty and num_questions):
        print("⚠️ Incomplete session data, redirecting to categories")
        return redirect('categories')

    questions = AIQuestion.objects.filter(
        category=category,
        subcategory=subcategory,
        difficulty=difficulty,
    ).order_by('-created_at')[:int(num_questions)]

    if not questions.exists():
        print("❌ No questions found for this quiz configuration")
        return redirect('categories')

    question_ids = [q.id for q in questions]
    request.session['quiz_question_ids'] = question_ids

    # Always start a new attempt if nothing in session or old attempt is completed
    attempt = None
    attempt_id = request.session.get('current_attempt_id')
    
    if attempt_id:
        try:
            attempt = UserQuizAttempt.objects.get(pk=attempt_id, user=request.user)
            # If attempt already completed, start a new one
            if attempt.completed:
                print(f"Previous attempt {attempt.id} was completed. Starting new attempt.")
                attempt = None
        except UserQuizAttempt.DoesNotExist:
            attempt = None

    if not attempt:
        attempt = UserQuizAttempt.objects.create(
            user=request.user,
            category=category,
            subcategory=subcategory,
            difficulty=difficulty,
            started_at=timezone.now()
        )
        request.session['current_attempt_id'] = attempt.id
        print(f"✅ New attempt {attempt.id} created")

    # Calculate timer based on difficulty and number of questions
    def calculate_timer(num_questions, difficulty):
        time_per_question = {
            'Easy': 60,      # 1 min per question
            'Medium': 90,    # 1.5 min per question
            'Hard': 120      # 2 min per question
        }
        seconds_per_q = time_per_question.get(difficulty, 90)
        return num_questions * seconds_per_q

    timer_seconds = calculate_timer(len(question_ids), difficulty)
    timer_minutes = timer_seconds // 60

    return render(request, "quizzes/quiz_start.html", {
        "questions": questions,
        "total_questions": len(question_ids),
        "category": category,
        "subcategory": subcategory,
        "difficulty": difficulty,
        "timer_seconds": timer_seconds,
        "timer_minutes": timer_minutes,
        "attempt_id": attempt.id,
    })


@login_required
def quiz_submit(request):
    """Process quiz submission and save answers"""
    if request.method == "POST":
        user = request.user
        attempt_id = request.session.get('current_attempt_id')
        question_ids = request.session.get('quiz_question_ids', [])

        if not attempt_id or not question_ids:
            print("⚠️ Missing attempt_id or question_ids")
            return redirect('quiz_start')

        try:
            attempt = UserQuizAttempt.objects.get(id=attempt_id, user=user)
        except UserQuizAttempt.DoesNotExist:
            print(f"❌ Attempt {attempt_id} not found")
            return redirect('quiz_start')

        # Prevent resubmission
        if attempt.completed:
            print(f"⚠️ Attempt {attempt_id} already completed")
            return redirect('quiz_results')

        correct_count = 0
        user_answers = {}

        # 🧠 Evaluate each question
        for qid in question_ids:
            answer = request.POST.get(f'question_{qid}', '').strip()
            
            if answer:
                try:
                    question_obj = get_object_or_404(AIQuestion, id=qid)
                    is_correct = (answer.lower() == question_obj.answer.strip().lower())

                    # 🧠 Generate explanation only for incorrect answers
                    explanation = ""
                    if not is_correct:
                        print(f"📚 Generating explanation for Q{qid}...")
                        explanation = call_ai_explanation_api(
                            question_obj.question_text,
                            question_obj.answer,
                            answer
                        )
                        # Auto-generate helpful reference
                        reference_link = f"https://www.google.com/search?q={question_obj.question_text.replace(' ', '+')}"
                        learning_source = "Google Search"
                    else:
                        explanation = ""
                        reference_link = ""
                        learning_source = ""

                    # Save or update UserAnswer with explanation
                    user_answer_obj, created = UserAnswer.objects.update_or_create(
                        attempt=attempt,
                        question=question_obj,
                        defaults={
                            'user_answer': answer,
                            'is_correct': is_correct,
                            'explanation': explanation,
                            'reference_link': reference_link,
                            'learning_source': learning_source,
                        },
                    )

                    if is_correct:
                        correct_count += 1

                    user_answers[str(qid)] = answer
                    
                except Exception as e:
                    print(f"❌ Error processing Q{qid}: {e}")
                    continue

        # ✅ Calculate score
        total_questions = len(question_ids)
        score_percentage = (correct_count / total_questions) * 100 if total_questions else 0

        # ✅ Mark quiz as completed
        attempt.score_percentage = score_percentage
        attempt.completed = True
        attempt.completed_at = timezone.now()
        attempt.save()

        UserActivity.objects.create(
            user=request.user,
            activity_type="Quiz Completed",
            description=f"Completed quiz in {attempt.category} ({attempt.subcategory})"
        )

        # ✅ Store answers & score in session
        request.session['quiz_answers'] = user_answers
        request.session['quiz_score'] = score_percentage

        print(f"✅ Quiz {attempt_id} submitted: {correct_count}/{total_questions} correct ({score_percentage:.1f}%)")

        return redirect('quiz_results')

    return redirect('quiz_start')


@login_required
def quiz_results(request):
    """Display quiz results with explanations and feedback options"""
    attempt_id = request.session.get('current_attempt_id')
    if not attempt_id:
        print("⚠️ No current attempt in session")
        return redirect('quiz_start')

    try:
        attempt = UserQuizAttempt.objects.get(id=attempt_id, user=request.user)
    except UserQuizAttempt.DoesNotExist:
        print(f"❌ Attempt {attempt_id} not found")
        return redirect('quiz_start')

    # Pull the questions for THIS attempt from session
    question_ids = request.session.get('quiz_question_ids', [])

    total_questions = len(question_ids)
    
    if total_questions == 0:
        print("⚠️ No questions in session")
        return redirect('quiz_start')

    # Optimize query with select_related
    questions = AIQuestion.objects.filter(id__in=question_ids)
    answers_qs = attempt.answers.select_related('question')
    user_ans_dict = {ua.question_id: ua for ua in answers_qs}

    result_list = []
    correct_count = 0

    for q in questions:
        ua = user_ans_dict.get(q.id)
        if ua:
            is_correct = ua.is_correct
            user_answer = ua.user_answer
            explanation = ua.explanation
        else:
            is_correct = False
            user_answer = None
            explanation = ""

        if is_correct:
            correct_count += 1

        result_list.append({
            'question': q,
            'user_answer': user_answer,
            'is_correct': is_correct,
            'answer_id': ua.id if ua else None,
            'explanation': explanation,
            'reference_link': getattr(ua, 'reference_link', ''),
            'learning_source': getattr(ua, 'learning_source', ''),
        })

    score_percentage = (correct_count / total_questions) * 100 if total_questions else 0

    # Performance feedback
    if score_percentage >= 80:
        performance = "Excellent! 🌟"
    elif score_percentage >= 60:
        performance = "Good Job! 👍"
    elif score_percentage >= 40:
        performance = "Not Bad! 📚 Keep practicing!"
    else:
        performance = "Keep Learning! 💪"

    return render(request, "quizzes/quiz_results.html", {
        "answers": result_list,
        "attempt": attempt,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "score_percentage": score_percentage,
        "performance": performance,
    })


@login_required
def categories_view(request):
    """
    Display all available quiz categories
    """
    categories = Category.objects.all().prefetch_related('subcategories')
    
    context = {
        'categories': categories,
    }
    return render(request, 'quizzes/categories.html', context)



# New view: quiz_history
@login_required
def quiz_history(request):
    """
    Quiz History page:
      - server-side filtering (category, subcategory, search)
      - pagination with rows-per-page
      - supplies `subcategories_map` as JSON-safe dict
      - context variables expected by the improved template:
          categories (list of names),
          subcategories_map (JSON-safe),
          completed_quizzes (page object list),
          completed_page (Paginator page object),
          ongoing_quizzes,
          rows (string)
    """
    user = request.user

    # GET params
    page = request.GET.get('page', '1')
    rows = request.GET.get('rows', '10')  # default 10
    category_q = request.GET.get('category', '').strip()
    subcategory_q = request.GET.get('subcategory', '').strip()
    search_q = request.GET.get('search', '').strip()

    # Build base queryset for completed quizzes
    completed_qs = UserQuizAttempt.objects.filter(user=user, completed=True).order_by('-completed_at')

    # Apply server-side filters if present
    if category_q:
        completed_qs = completed_qs.filter(category__iexact=category_q)
    if subcategory_q:
        completed_qs = completed_qs.filter(subcategory__iexact=subcategory_q)

    if search_q:
        # Search across category, subcategory and (optionally) attempt id
        # Expand this Q if you have more fields to search (e.g., related question text)
        completed_qs = completed_qs.filter(
            Q(category__icontains=search_q) |
            Q(subcategory__icontains=search_q) |
            Q(id__icontains=search_q)
        )

    # Handle rows param (safe fallback)
    try:
        if rows.lower() == 'all':
            per_page = completed_qs.count() or 1
        else:
            per_page = int(rows)
            if per_page <= 0:
                per_page = 10
    except Exception:
        per_page = 10
        rows = '10'

    # Paginator
    paginator = Paginator(completed_qs, per_page)
    try:
        completed_page = paginator.page(page)
    except PageNotAnInteger:
        completed_page = paginator.page(1)
    except EmptyPage:
        completed_page = paginator.page(paginator.num_pages)

    # What the template expects: list of attempts for current page
    completed_quizzes = completed_page.object_list

    # Ongoing quizzes (not completed)
    ongoing_quizzes = UserQuizAttempt.objects.filter(user=user, completed=False).order_by('-started_at')

    # Categories and subcategories map
    # Build a dict: { "CategoryName": ["Subcat1","Subcat2", ...], ... }
    # Using Category/Subcategory models if available
    subcategories_map = {}
    categories_qs = Category.objects.prefetch_related('subcategories').all()
    categories = []
    for cat in categories_qs:
        categories.append(cat.name)
        sublist = [sc.name for sc in cat.subcategories.all()]
        subcategories_map[cat.name] = sublist

    # JSON-safe map for template JS
    try:
        subcategories_json = mark_safe(json.dumps(subcategories_map))
    except Exception:
        subcategories_json = mark_safe(json.dumps({}))

    context = {
        'categories': categories,                    # list of category names (template loops over these)
        'subcategories_map': subcategories_json,     # JSON-safe dict used by JS
        'completed_quizzes': completed_quizzes,      # current page's items
        'completed_page': completed_page,            # paginator page object
        'ongoing_quizzes': ongoing_quizzes,
        'rows': str(rows),
        # echo back filters so UI can pre-populate if desired
        'active_category': category_q,
        'active_subcategory': subcategory_q,
        'search_query': search_q,
    }
    return render(request, 'quizzes/quiz_history.html', context)
