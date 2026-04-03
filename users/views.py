from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Q, Avg, Count
from django.core.paginator import Paginator
from datetime import timedelta
from django.utils import timezone
import json
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm
from .models import Profile
from quizzes.models import UserQuizAttempt
from quizzes.models import UserQuizAttempt, UserAnswer, QuestionFeedback,Category, AIQuestion
from quizzes.models import UserActivity

# ============= AUTH VIEWS =============

def home_view(request):
    """Home page view"""
    return render(request, 'users/home.html')


def register_view(request):
    """User registration view"""
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        username = request.POST.get('username')

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            messages.error(request, f"The username '{username}' is already taken. Please choose another one.")
            return render(request, 'users/register.html', {'form': form})

        if form.is_valid():
            user = form.save()
            Profile.objects.get_or_create(user=user)
            messages.success(request, f"Account created successfully for {user.username}! 🎉 Please log in.")
            return redirect('home')
        else:
            return render(request, 'users/register.html', {'form': form})
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    """User login view"""
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember = request.POST.get('remember')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if not remember:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(1209600)
            messages.success(request, 'Login successful! Welcome back.')
            return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
            return render(request, "users/login.html")
    
    return render(request, "users/login.html")


def logout_view(request):
    """User logout view"""
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('home')



@login_required
def profile_view(request):
    """
    Profile view and handler:
      - Handles profile update (username, email, avatar, bio)
      - Handles password change via PasswordChangeForm
      - Computes safe XP / level / progress from quiz attempts
      - Builds a 28-day activity heatmap from UserActivity
      - Derives simple badges from activity/stats (safe defaults)
    """
    user = request.user

    # Ensure profile exists
    Profile.objects.get_or_create(user=user)

    # Initialize forms
    u_form = UserUpdateForm(instance=user)
    p_form = ProfileUpdateForm(instance=user.profile)
    pw_form = PasswordChangeForm(user=request.user)

    # Decide which form was submitted using a hidden input name
    if request.method == 'POST':
        # Distinguish between forms by a hidden input 'form_type'
        form_type = request.POST.get('form_type', 'profile')

        if form_type == 'profile':
            u_form = UserUpdateForm(request.POST, instance=user)
            p_form = ProfileUpdateForm(request.POST, request.FILES, instance=user.profile)
            if u_form.is_valid() and p_form.is_valid():
                u_form.save()
                p_form.save()
                messages.success(request, '✅ Your profile has been updated successfully!')
                return redirect('profile')
            else:
                messages.error(request, 'Please fix the errors in the form.')
        elif form_type == 'password':
            pw_form = PasswordChangeForm(user=request.user, data=request.POST)
            # Keep u_form and p_form so the page re-renders consistently
            if pw_form.is_valid():
                user = pw_form.save()
                # Important: keep the user logged in after password change
                update_session_auth_hash(request, user)
                messages.success(request, '✅ Your password has been updated successfully.')
                return redirect('profile')
            else:
                messages.error(request, 'Please fix the password errors.')

    # ------------------ Stats / XP / Heatmap (defensive) ------------------
    # Completed attempts
    attempts = UserQuizAttempt.objects.filter(user=user, completed=True)
    total_quizzes = attempts.count()

    # Average score
    avg_score_value = attempts.aggregate(avg=Avg('score_percentage'))['avg']
    avg_score = round(avg_score_value, 2) if avg_score_value else 0

    # Rank (safe)
    ranked_users = (
        UserQuizAttempt.objects.filter(completed=True)
        .values('user')
        .annotate(avg_score=Avg('score_percentage'))
        .order_by('-avg_score')
    )
    user_rank = "-"
    for idx, entry in enumerate(ranked_users, start=1):
        if entry["user"] == user.id:
            user_rank = idx
            break

    # XP calculation (simple derived metric)
    # XP = sum of score percentages (rounded), fallback to 0
    try:
        xp_current = int(sum((a.score_percentage or 0) for a in attempts))
    except Exception:
        xp_current = 0
    # xp_target: set relative to activity; at least 1000
    xp_target = max(1000, total_quizzes * 200, 1000)
    xp_percent = int((xp_current / max(1, xp_target)) * 100)
    xp_percent = max(0, min(100, xp_percent))

    # Level label (very simple)
    if xp_percent >= 90:
        level = "Master"
    elif xp_percent >= 70:
        level = "Expert"
    elif xp_percent >= 40:
        level = "Intermediate"
    else:
        level = "Learner"

    # Heatmap for last 28 days (using UserActivity timestamp__date)
    heatmap_days = 28
    today = timezone.now().date()
    heatmap_grid = []
    heatmap_counts = []
    for i in range(heatmap_days - 1, -1, -1):
        d = today - timedelta(days=i)
        try:
            cnt = UserActivity.objects.filter(user=user, timestamp__date=d).count()
        except Exception:
            cnt = 0
        heatmap_counts.append(cnt)
        # map count to color (same palette as template)
        if cnt == 0:
            color = '#e4e8ed'
        elif cnt == 1:
            color = '#c9d6ff'
        elif cnt <= 3:
            color = '#8F85FF'
        elif cnt <= 6:
            color = '#6C63FF'
        else:
            color = '#4533A5'
        heatmap_grid.append({'date': d.isoformat(), 'count': cnt, 'color': color})

    # Badges: derive some simple badges from user stats (safe)
    badges = []
    try:
        # Beginner badge if at least 1 quiz
        badges.append({'name': 'Beginner', 'icon': 'bi-star-fill', 'level': 'bronze', 'earned': total_quizzes >= 1})
        # Consistency badge if had activity 7+ days in last 28
        active_days = sum(1 for c in heatmap_counts if c > 0)
        badges.append({'name': 'Consistent Learner', 'icon': 'bi-fire', 'level': 'silver', 'earned': active_days >= 7})
        # High Performer if avg_score >= 80
        badges.append({'name': 'High Performer', 'icon': 'bi-award-fill', 'level': 'gold', 'earned': avg_score >= 80})
    except Exception:
        badges = [
            {'name': 'Beginner', 'icon': 'bi-star-fill', 'level': 'bronze', 'earned': True},
            {'name': 'Consistent', 'icon': 'bi-fire', 'level': 'silver', 'earned': False},
            {'name': 'Top Scorer', 'icon': 'bi-award-fill', 'level': 'gold', 'earned': False},
        ]

    # Context (include forms, stats, xp, heatmap, badges)
    context = {
        'u_form': u_form,
        'p_form': p_form,
        'pw_form': pw_form,
        'total_quizzes': total_quizzes,
        'avg_score': avg_score,
        'user_rank': user_rank,
        'xp_current': xp_current,
        'xp_target': xp_target,
        'xp_percent': xp_percent,
        'level': level,
        'heatmap_grid': heatmap_grid,
        'heatmap_data': json.dumps(heatmap_counts),
        'badges': badges,
    }

    return render(request, 'users/profile.html', context)



# ============= QUIZ/DASHBOARD VIEWS =============

def categories_view(request):
    """Categories page view"""
    return render(request, 'categories.html')


@login_required
def my_quizzes_view(request):
    user = request.user
    attempts = UserQuizAttempt.objects.filter(user=user)

    # Filters
    category = request.GET.get('category')
    subcategory = request.GET.get('subcategory')
    search = request.GET.get('search')
    rows = request.GET.get('rows', "10")
    page_number = request.GET.get('page', 1)

    if category:
        attempts = attempts.filter(category__iexact=category)
    if subcategory:
        attempts = attempts.filter(subcategory__iexact=subcategory)
    if search:
        attempts = attempts.filter(Q(category__icontains=search) | Q(subcategory__icontains=search))

    completed = attempts.filter(completed=True).order_by('-completed_at')
    ongoing = attempts.filter(completed=False).order_by('-started_at')

    # Stats for dashboard
    completed_attempts = UserQuizAttempt.objects.filter(user=user, completed=True)
    total_quizzes = completed_attempts.count()
    avg_score = completed_attempts.aggregate(Avg('score_percentage'))['score_percentage__avg'] or 0
    total_time_seconds = sum((a.completed_at - a.started_at).total_seconds() for a in completed_attempts if a.completed_at and a.started_at)
    total_time_str = f"{int(total_time_seconds // 60)} min"

    # Category breakdown (pie chart)
    category_stats = list(
        completed_attempts.values('category').annotate(avg=Avg('score_percentage'), count=Count('id'))
    )
    pie_labels = [c['category'] for c in category_stats]
    pie_data = [c['count'] for c in category_stats]
    pie_json = {
        "labels": pie_labels,
        "datasets": [{
            "label": "Quiz Count",
            "data": pie_data,
            "backgroundColor": [
                "#2e83ff", "#46e6b6", "#ffab00", "#e64b3c",
                "#c03cbf", "#3cbe7a", "#FFD642", "#A3A3FB"
            ]
        }]
    }

    # Score Progress (line chart, last 8 weeks)
    today = timezone.now().date()
    week_labels = []
    week_scores = []
    for i in range(7, -1, -1):  # last 8 weeks (oldest first)
        week_start = today - timedelta(days=7 * i)
        week_end = week_start + timedelta(days=6)
        avg_score_wk = completed_attempts.filter(
            completed_at__date__gte=week_start,
            completed_at__date__lte=week_end
        ).aggregate(val=Avg('score_percentage'))['val'] or 0
        week_labels.append(week_start.strftime("Week %W"))
        week_scores.append(round(avg_score_wk, 2))
    score_progress_data = {
        "labels": week_labels,
        "datasets": [{
            "label": "Avg Score",
            "data": week_scores,
            "borderColor": "#46A0FF",
            "backgroundColor": "#46A0FF22",
            "tension": 0.2,
            "fill": True,
            "pointRadius": 4
        }]
    }

    # Time Spent Analytics (bar chart, last 8 weeks)
    time_spent_per_week = []
    for i in range(7, -1, -1):
        week_start = today - timedelta(days=7 * i)
        week_end = week_start + timedelta(days=6)
        attempts_wk = completed_attempts.filter(
            completed_at__date__gte=week_start,
            completed_at__date__lte=week_end
        )
        total_seconds_wk = sum(
            (a.completed_at - a.started_at).total_seconds()
            for a in attempts_wk if a.completed_at and a.started_at)
        time_spent_per_week.append(round(total_seconds_wk / 60, 2))  # MINUTES
    time_spent_data = {
        "labels": week_labels,
        "datasets": [{
            "label": "Minutes Spent",
            "data": time_spent_per_week,
            "backgroundColor": "#FFD642"
        }]
    }

    # Best and Needs Improvement
    best_attempt = completed_attempts.order_by('-score_percentage').first()
    needs_improve = completed_attempts.order_by('score_percentage').first()

    # Recent Activities (last 10)
    recent_activities = UserActivity.objects.filter(user=user).order_by('-timestamp')[:5]

    # Pagination logic
    if str(rows) == "All":
        rows_count = completed.count() or 1
    else:
        try:
            rows_count = int(rows)
        except ValueError:
            rows_count = 10

    paginator = Paginator(completed, rows_count)
    completed_page = paginator.get_page(page_number)

    # Calculate time taken string for each attempt
    attempts_with_time = []
    for attempt in completed_page:
        if attempt.started_at and attempt.completed_at:
            delta = attempt.completed_at - attempt.started_at
            if delta.total_seconds() < 60:
                time_taken_str = f"{int(delta.total_seconds())} sec"
            elif delta.total_seconds() < 3600:
                mins = int(delta.total_seconds() // 60)
                time_taken_str = f"{mins} min"
            else:
                hours = int(delta.total_seconds() // 3600)
                mins = int((delta.total_seconds() % 3600) // 60)
                time_taken_str = f"{hours} hr {mins} min"
        else:
            time_taken_str = "-"
        attempt.time_taken_str = time_taken_str
        attempts_with_time.append(attempt)

    categories = UserQuizAttempt.objects.values_list('category', flat=True).distinct()
    subcategories = UserQuizAttempt.objects.values_list('subcategory', flat=True).distinct()

    context = {
        'completed_quizzes': attempts_with_time,
        'completed_page': completed_page,
        'ongoing_quizzes': ongoing,
        'categories': categories,
        'subcategories': subcategories,
        'page_obj': completed_page,
        'rows': rows,
        'total_quizzes': total_quizzes,
        'avg_score': avg_score,
        'total_time_str': total_time_str,
        'pie_data': json.dumps(pie_json),
        'score_progress_data': json.dumps(score_progress_data),
        'time_spent_data': json.dumps(time_spent_data),
        'recent_activities': recent_activities,
        'best_attempt': best_attempt,
        'needs_improve': needs_improve,
    }

    return render(request, "users/dashboard.html", context)


# ============= QUIZ REVIEW/FEEDBACK VIEWS =============

@login_required
def review_quiz_view(request, attempt_id):
    attempt = UserQuizAttempt.objects.get(id=attempt_id, user=request.user)
    answers = UserAnswer.objects.filter(attempt=attempt).select_related('question')
    questions = []
    for answer in answers:
        feedback = QuestionFeedback.objects.filter(
            user=request.user, question_id=answer.question.id
        ).order_by('-id').first()
        questions.append({
            'id': answer.question.id,
            'text': answer.question.question_text,
            'user_answer': answer.user_answer,
            'correct_answer': answer.question.answer,
            'is_correct': answer.is_correct,
            'explanation': answer.explanation,
            'reference_link': getattr(answer, 'reference_link', ''),
            'learning_source': getattr(answer, 'learning_source', ''),
            'user_feedback': feedback.feedback_type if feedback else "",
            'user_text_feedback': feedback.feedback_text if (feedback and feedback.feedback_text) else "",
        })

    # --- Calculate time taken string ---
    if attempt.started_at and attempt.completed_at:
        delta = attempt.completed_at - attempt.started_at
        if delta.total_seconds() < 60:
            time_taken_str = f"{int(delta.total_seconds())} sec"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() // 60)
            time_taken_str = f"{mins} min"
        else:
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            time_taken_str = f"{hours} hr {mins} min"
    else:
        time_taken_str = "-"

    context = {
        'attempt': attempt,
        'questions': questions,
        'time_taken_str': time_taken_str,  # pass it to template!
    }
    return render(request, 'users/review_quiz.html', context)

@login_required
def retake_quiz_view(request, attempt_id):
    """Allow user to retake the same quiz by creating a new attempt"""
    try:
        old_attempt = UserQuizAttempt.objects.get(id=attempt_id, user=request.user)
    except UserQuizAttempt.DoesNotExist:
        return redirect('categories')
    
    # Create new attempt with same parameters
    new_attempt = UserQuizAttempt.objects.create(
        user=request.user,
        category=old_attempt.category,
        subcategory=old_attempt.subcategory,
        difficulty=old_attempt.difficulty,
        started_at=timezone.now(),
        completed=False,
        score_percentage=0,
    )


    UserActivity.objects.create(
        user=request.user,
        activity_type="Quiz Retaken",
        description=f"Retook quiz in {old_attempt.category} ({old_attempt.subcategory})"
    )


    
    # ✅ Store session data for quiz
    request.session['current_attempt_id'] = new_attempt.id
    request.session['ai_category'] = old_attempt.category
    request.session['ai_subcategory'] = old_attempt.subcategory
    request.session['ai_difficulty'] = old_attempt.difficulty
    
    # Redirect to categories to select difficulty/questions again
    # Or directly to quiz_start
    return redirect('quiz_start')



@login_required
def continue_quiz_view(request, attempt_id):
    """Allow user to continue an ongoing quiz"""
    try:
        attempt = UserQuizAttempt.objects.get(id=attempt_id, user=request.user, completed=False)
        

        UserActivity.objects.create(
            user=request.user,
            activity_type="Quiz Continued",
            description=f"Continued quiz in {attempt.category} ({attempt.subcategory})"
        )


        # Store attempt ID in session
        request.session['current_attempt_id'] = attempt.id
        
        # Redirect to quiz start to continue
        return redirect('quiz_start')
    
    except UserQuizAttempt.DoesNotExist:
        # Redirect to dashboard if attempt not found
        return redirect('my_quizzes')


@login_required
def give_feedback(request, answer_id):
    """Record if an answer explanation was helpful"""
    if request.method == "POST":
        answer = get_object_or_404(UserAnswer, id=answer_id, attempt__user=request.user)
        helpful = request.POST.get("helpful") == "true"
        answer.helpful_feedback = helpful
        answer.save()
    return redirect(request.META.get("HTTP_REFERER", "my_quizzes"))

@login_required
def quiz_history_view(request):
    user = request.user
    base_attempts = UserQuizAttempt.objects.filter(user=user)

    # Get filter and sort params
    category = request.GET.get('category', '').strip()
    search = request.GET.get('search', '').strip()
    sort = request.GET.get('sort', '')
    rows = request.GET.get('rows', '10').strip().lower()
    page_number = request.GET.get('page', 1)

    # --- FILTERS (only for completed) ---
    completed_attempts = base_attempts.filter(completed=True)
    if category:
        completed_attempts = completed_attempts.filter(category__iexact=category)
    if search:
        completed_attempts = completed_attempts.filter(
            Q(category__icontains=search) | Q(score_percentage__icontains=search)
        )
    
    # --- SORTING ---
    if sort == "oldest":
        completed_attempts = completed_attempts.order_by('completed_at')
    elif sort == "highest":
        completed_attempts = completed_attempts.order_by('-score_percentage', '-completed_at')
    elif sort == "lowest":
        completed_attempts = completed_attempts.order_by('score_percentage', '-completed_at')
    elif sort == "alpha":
        completed_attempts = completed_attempts.order_by('category', '-completed_at')
    else:  # Newest (default)
        completed_attempts = completed_attempts.order_by('-completed_at')

    # --- PAGINATION ---
    if rows in ("all", "100"):
        rows_count = completed_attempts.count() or 1
    else:
        try:
            rows_count = int(rows)
        except ValueError:
            rows_count = 10
    paginator = Paginator(completed_attempts, rows_count)
    completed_page = paginator.get_page(page_number)

    # --- Calculate time taken for each attempt ---
    attempts_with_time = []
    for attempt in completed_page:
        if attempt.started_at and attempt.completed_at:
            delta = attempt.completed_at - attempt.started_at
            if delta.total_seconds() < 60:
                time_taken_str = f"{int(delta.total_seconds())} sec"
            elif delta.total_seconds() < 3600:
                mins = int(delta.total_seconds() // 60)
                time_taken_str = f"{mins} min"
            else:
                hours = int(delta.total_seconds() // 3600)
                mins = int((delta.total_seconds() % 3600) // 60)
                time_taken_str = f"{hours} hr {mins} min"
        else:
            time_taken_str = "-"
        attempt.time_taken_str = time_taken_str
        attempts_with_time.append(attempt)

    # --- Ongoing: always unfiltered ---
    ongoing_quizzes = base_attempts.filter(completed=False).order_by('-started_at')

    # --- Categories for filter dropdown ---
    categories = (
        UserQuizAttempt.objects.filter(user=user)
        .values_list('category', flat=True)
        .distinct()
    )

    context = {
        'completed_quizzes': attempts_with_time,
        'completed_page': completed_page,
        'ongoing_quizzes': ongoing_quizzes,
        'categories': categories,
        'category': category,
        'search': search,
        'rows': rows,
        'sort': sort,
    }
    return render(request, "users/history.html", context)
# ============= FEEDBACK VIEWS (AJAX) =============

@csrf_exempt
@login_required
def submit_feedback_view(request):
    if request.method == "POST":
        data = json.loads(request.body)
        qid = data.get('question_id')
        ftype = data.get('feedback_type')
        fb, _ = QuestionFeedback.objects.update_or_create(
            user=request.user, question_id=qid,
            defaults={'feedback_type': ftype}
        )
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)


@csrf_exempt
@login_required
def submit_text_feedback_view(request):
    """Save text feedback via AJAX (updates or creates)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            qid = data.get('question_id')
            feedback_text = data.get('feedback_text')
            # Try to get existing feedback
            fb, created = QuestionFeedback.objects.get_or_create(
                user=request.user, question_id=qid,
                defaults={'feedback_text': feedback_text, 'feedback_type': 'text'}
            )
            if not created:
                # Only update fields if the record already exists
                fb.feedback_text = feedback_text
                # Optional: If you want to mark this as a text edit, set type:
                fb.feedback_type = fb.feedback_type or 'text'
                fb.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False}, status=400)



@login_required
def help_view(request):
    return render(request, 'users/help.html')

def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  
            messages.success(request, "Password updated successfully!")
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "users/change_password.html", {"form": form})