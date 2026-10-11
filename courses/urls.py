from django.urls import path

from . import views

urlpatterns = [
    path("", views.course_list, name="course_list"),
    path("<int:course_id>/", views.course_detail, name="course_detail"),
    path("modules/<int:module_id>/", views.module_detail, name="module_detail"),
    path("modules/<int:module_id>/complete/", views.complete_content, name="complete_content"),
    path("modules/<int:module_id>/video-checkpoint/", views.video_checkpoint, name="video_checkpoint"),
]
