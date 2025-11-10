from django.urls import path
from . import views
from .views import quiz_start, quiz_submit, quiz_results

urlpatterns = [
    path('category/<int:category_id>/select/', views.subcategory_selection, name='subcategory_selection'),
    path('quiz/start/', quiz_start, name='quiz_start'),
    path('quiz/submit/', quiz_submit, name='quiz_submit'),
    path('quiz/results/', quiz_results, name='quiz_results'),
]
