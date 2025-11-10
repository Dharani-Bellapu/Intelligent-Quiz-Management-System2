from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

class Subcategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')

class Quiz(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='quizzes')
    subcategory = models.ForeignKey(Subcategory, on_delete=models.CASCADE, related_name='quizzes')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    status = models.BooleanField(default=True)
    total_questions = models.IntegerField(default=10)
    time_limit = models.IntegerField(default=15, help_text="Time limit in minutes")
    score = models.IntegerField(default=0)
    quiz_status = models.CharField(max_length=20, default='inactive')

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_1 = models.CharField(max_length=255)
    option_2 = models.CharField(max_length=255)
    option_3 = models.CharField(max_length=255)
    option_4 = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=255)

class AIQuestion(models.Model):
    category = models.CharField(max_length=100)
    subcategory = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=20)
    question_text = models.TextField()
    options = models.JSONField()  # list of options
    answer = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)
    reviewer_notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.question_text[:80]}"

class UserQuizAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attempts')
    category = models.CharField(max_length=100, default="General")
    subcategory = models.CharField(max_length=100, default="General")
    difficulty = models.CharField(max_length=20, default="Easy")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score_percentage = models.FloatField(default=0)
    completed = models.BooleanField(default=False)

class UserAnswer(models.Model):
    attempt = models.ForeignKey(UserQuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(AIQuestion, on_delete=models.CASCADE)
    user_answer = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
