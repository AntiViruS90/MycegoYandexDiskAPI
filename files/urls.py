from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('download/<str:public_key>/<path:file_path>', views.download_file, name='download_file'),
    re_path(r'^download_multiple/(?P<public_key>.+)/$', views.download_multiple_files, name='download_multiple_files'),
]
