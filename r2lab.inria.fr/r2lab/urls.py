"""r2lab URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.contrib import admin

from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView

urlpatterns = [
    url(r'^(/)?$', RedirectView.as_view(url='/index', permanent=False), name='index'),
    url(r'^admin/', admin.site.urls),
    url(r'^md/', include('md.urls')),
] \
    + static( '/assets/', document_root=settings.BASE_DIR+'/assets/') \
    + static( '/plugins/', document_root=settings.BASE_DIR+'/plugins/') \
    + static( '/codes_examples/', document_root=settings.BASE_DIR+'/codes_examples/') \
+ [
    # default -> md/
    # very rough - see md/views.py
    url(r'^(?P<toplevel_markdown_file>.*)$', include('md.urls')),
]

