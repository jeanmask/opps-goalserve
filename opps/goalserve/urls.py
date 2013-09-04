# -*- coding: utf-8 -*-
from django.conf.urls import patterns, include
from opps.goalserve.views import (match, ajax_categories_by_country_name,
                                  ajax_match_by_category_id, ajax_get_matches, get_task_status)

from tastypie.api import Api
from opps.goalserve.api import PlayerResource

v1_api = Api(api_name='v1')
v1_api.register(PlayerResource())

urlpatterns = patterns('',
    (r'^match/(?P<match_pk>\d+)/(?P<mode>\w+)/$', match, {}, 'match'),
    (r'^match/(?P<match_pk>\d+)/$', match, {}, 'match'),
    (r'^ajax_categories_by_country_name/(?P<country_name>\w+)/$',
        ajax_categories_by_country_name, {}, 'ajax_categories_by_country_name'),
    (r'^ajax_match_by_category_id/(?P<category_id>\d+)/$',
        ajax_match_by_category_id, {}, 'ajax_match_by_category_id'),
    (r'^ajax_get_matches/(?P<country_name>\w+)/$', ajax_get_matches, {}, 'ajax_get_matches'),
    (r'^ajax_get_matches/(?P<country_name>\w+)/(?P<match_id>\d+)/$',
        ajax_get_matches, {}, 'ajax_get_matches_id'),
    (r'^get_task_status/(?P<task_id>[\w-]+)/$', get_task_status, {}, 'get_task_status'),
    (r'^api/', include(v1_api.urls)),
)
