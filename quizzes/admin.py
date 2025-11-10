from django.contrib import admin
from .models import Category, Subcategory, Quiz, Question, UserQuizAttempt, UserAnswer
from .models import AIQuestion

admin.site.register(Category)
admin.site.register(Subcategory)
admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(UserQuizAttempt)
admin.site.register(UserAnswer)


@admin.register(AIQuestion)
class AIQuestionAdmin(admin.ModelAdmin):
    list_display = ("category", "subcategory", "difficulty", "question_text", "reviewed", "created_at")
    list_filter = ("category", "subcategory", "difficulty", "reviewed")
    search_fields = ("question_text",)
    actions = ["mark_as_reviewed"]

    def mark_as_reviewed(self, request, queryset):
        queryset.update(reviewed=True)
    mark_as_reviewed.short_description = "Mark selected questions as reviewed"