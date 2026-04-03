from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from . import views

# ✅ IMPORT ALL THE VIEWS YOU'RE USING
from .views import (
    home_view,
    register_view,
    login_view,
    logout_view,
    profile_view,
    categories_view,
    my_quizzes_view,
    give_feedback,
    review_quiz_view,
    retake_quiz_view,
    continue_quiz_view,
    submit_feedback_view,
    submit_text_feedback_view,
)

urlpatterns = [
    # Auth Views
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('change-password/', views.change_password, name='change_password'),


    # Password Reset Views
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='password_reset.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='password_reset_complete.html'), name='password_reset_complete'),
    
    # Quiz & Dashboard Views
    path('categories/', views.categories_view, name='categories'),
    path('my-quizzes/', views.my_quizzes_view, name='my_quizzes'),
    path('quizzes/history/', views.quiz_history_view, name='history'),

    # Quiz Review Views
    path('quiz/<int:attempt_id>/review/', views.review_quiz_view, name='review_quiz'),
    path('quiz/<int:attempt_id>/retake/', views.retake_quiz_view, name='retake_quiz'),
    path('quiz/<int:attempt_id>/continue/', views.continue_quiz_view, name='continue_quiz'),
    
    # Feedback Views
    path('give-feedback/<int:answer_id>/', views.give_feedback, name='give_feedback'),
    path('feedback/submit/', views.submit_feedback_view, name='submit_feedback'),
    path('feedback/text/', views.submit_text_feedback_view, name='submit_text_feedback'),

    path('help/', views.help_view, name='help_page'),
]

# Serve media files in development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
