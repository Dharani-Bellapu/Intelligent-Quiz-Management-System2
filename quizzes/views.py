from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import Category, Subcategory, AIQuestion, UserQuizAttempt, UserAnswer
from .services.ai_questions import generate_questions


@login_required
def subcategory_selection(request, category_id):
    category = get_object_or_404(Category, pk=category_id)
    subcategories = category.subcategories.all()

    if request.method == "POST":
        subcategory_id = request.POST.get("subcategory")
        difficulty = request.POST.get("difficulty").capitalize()
        num_questions = request.POST.get("num_questions")

        if subcategory_id and difficulty and num_questions:
            subcat = get_object_or_404(Subcategory, pk=subcategory_id)
            num_questions = int(num_questions)

            # Generate questions using AI service
            questions = generate_questions(
                category.name,
                subcat.name,
                difficulty,
                num_questions,
            )

            # Cache questions in database
            for q in questions:
                AIQuestion.objects.create(
                    category=category.name,
                    subcategory=subcat.name,
                    difficulty=difficulty,
                    question_text=q["question"],
                    options=q["options"],
                    answer=q["answer"],
                )

            # Store quiz metadata in session
            request.session['ai_category'] = category.name
            request.session['ai_subcategory'] = subcat.name
            request.session['ai_difficulty'] = difficulty
            request.session['ai_num_questions'] = num_questions

            return redirect('quiz_start')

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
    category = request.session.get('ai_category')
    subcategory = request.session.get('ai_subcategory')
    difficulty = request.session.get('ai_difficulty')
    num_questions = request.session.get('ai_num_questions')

    if not (category and subcategory and difficulty and num_questions):
        return redirect('subcategory_selection')

    questions = AIQuestion.objects.filter(
        category=category,
        subcategory=subcategory,
        difficulty=difficulty,
    ).order_by('-created_at')[:int(num_questions)]

    question_ids = [q.id for q in questions]
    request.session['quiz_question_ids'] = question_ids

    # Create or reuse UserQuizAttempt
    attempt_id = request.session.get('current_attempt_id')
    if attempt_id:
        attempt = get_object_or_404(UserQuizAttempt, pk=attempt_id, user=request.user)
    else:
        attempt = UserQuizAttempt.objects.create(
            user=request.user,
            category=category,
            subcategory=subcategory,
            difficulty=difficulty,
        )
        request.session['current_attempt_id'] = attempt.id

    # Calculate dynamic timer based on difficulty and number of questions
    def calculate_timer(num_questions, difficulty):
        time_per_question = {
            'Easy': 60,
            'Medium': 90,
            'Hard': 120,
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
    })


@login_required
def quiz_submit(request):
    if request.method == "POST":
        user = request.user
        attempt_id = request.session.get('current_attempt_id')
        question_ids = request.session.get('quiz_question_ids', [])

        if not attempt_id or not question_ids:
            return redirect('quiz_start')

        attempt = get_object_or_404(UserQuizAttempt, id=attempt_id, user=user)

        correct_count = 0
        user_answers = {}

        for qid in question_ids:
            answer = request.POST.get(f'question_{qid}', '')
            if answer:
                question_obj = get_object_or_404(AIQuestion, id=qid)
                is_correct = (answer == question_obj.answer)
                if is_correct:
                    correct_count += 1

                UserAnswer.objects.update_or_create(
                    attempt=attempt,
                    question=question_obj,
                    defaults={
                        'user_answer': answer,
                        'is_correct': is_correct,
                    },
                )
                user_answers[str(qid)] = answer

        total_questions = len(question_ids)
        score_percentage = (correct_count / total_questions) * 100 if total_questions else 0

        # Mark quiz as completed
        attempt.score_percentage = score_percentage
        attempt.completed = True
        attempt.completed_at = timezone.now()
        attempt.save()

        request.session['quiz_answers'] = user_answers
        request.session['quiz_score'] = score_percentage

        return redirect('quiz_results')

    return redirect('quiz_start')


@login_required
def quiz_results(request):
    attempt_id = request.session.get('current_attempt_id')
    if not attempt_id:
        return redirect('quiz_start')

    attempt = get_object_or_404(UserQuizAttempt, id=attempt_id, user=request.user)

    # Pull ONLY the questions for THIS attempt from session
    question_ids = request.session.get('quiz_question_ids', [])
    print("DEBUG: question_ids from session =", question_ids)  # Debug line

    total_questions = len(question_ids)
    print("DEBUG: total_questions =", total_questions)  # Debug line

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
        else:
            is_correct = False
            user_answer = None
        if is_correct:
            correct_count += 1
        result_list.append({
            'question': q,
            'user_answer': user_answer,
            'is_correct': is_correct
        })

    print("DEBUG: correct_count =", correct_count)  # Debug line

    score_percentage = (correct_count / total_questions) * 100 if total_questions else 0

    return render(request, "quizzes/quiz_results.html", {
        "answers": result_list,
        "attempt": attempt,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "score_percentage": score_percentage,
    })
