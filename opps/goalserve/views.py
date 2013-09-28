# -*- coding: utf-8 -*-
from django.http import HttpResponse
from django.http import StreamingHttpResponse
from django.shortcuts import render_to_response
from django.contrib.auth.decorators import login_required
from django.views.generic.edit import FormView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from opps.db import Db
from opps.views.generic.json_views import JSONResponse, JSONPResponse, JSONView

from .models import Match, Category, Driver, F1Team
from .models import MatchLineUp, Player, Team
from .tasks import get_matches
from .utils import data_match, serialize, get_tournament_standings
from .forms import LineupAddForm, LineupEditForm

from celery.result import AsyncResult
from dateutil.tz import tzutc
import time

UTC = tzutc()


class CSRFExemptMixin(object):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(CSRFExemptMixin, self).dispatch(*args, **kwargs)

        
class LoginRequiredMixin(object):
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(LoginRequiredMixin, self).dispatch(*args, **kwargs)
        

class SuccessURLMixin(object):
    def get_success_url(self):
        return self.request.path + "?status=success"

        
class LineupAddView(CSRFExemptMixin, LoginRequiredMixin, SuccessURLMixin, FormView):
    template_name = 'goalserve/lineupform.html'
    form_class = LineupAddForm

    def get_initial(self):
        initial = {}
        for field in self.form_class.base_fields.keys():
            if field in self.request.GET:
                initial[field] = self.request.GET.get(field)
        return initial
        
    def form_valid(self, form):
        data = form.cleaned_data
        match = Match.objects.get(pk=data.get('match_id'))
        team = Team.objects.get(pk=data.get('team_id'))
        player = Player.objects.create(
            name=data.get('player_name'),
            number=data.get('player_number'),
            position=data.get('player_position'),
            team=team
        )

        MatchLineUp.objects.create(
            team=team,
            player=player,
            player_position=player.position,
            player_number=player.number,
            match=match,
            player_status=data.get('player_status'),
            team_status=data.get('team_status'),
        )
        
        return super(LineupAddView, self).form_valid(form)
        

class LineupEditView(CSRFExemptMixin, LoginRequiredMixin, SuccessURLMixin, FormView):
    template_name = 'goalserve/lineupform.html'
    form_class = LineupEditForm

    def get_initial(self):
        initial = {}
        for field in self.form_class.base_fields.keys():
            if field in self.request.GET:
                initial[field] = self.request.GET.get(field)
        return initial

    def form_valid(self, form):
        data = form.cleaned_data
        lineup = MatchLineUp.objects.get(
            pk=data.get('lineup_id'))

        lineup.player.name = data.get('player_name')
        lineup.player.position = data.get('player_position')
        lineup.player.number = data.get('player_number')
        lineup.player.save()

        lineup.player_position = data.get('player_position')
        lineup.player_number = data.get('player_number')
        lineup.player_status = data.get('player_status')
        lineup.save()

        return super(LineupEditView, self).form_valid(form)


@login_required
def lineup_delete(request):
    match_id = request.REQUEST.get('match_id')
    lineup_id = request.REQUEST.get('lineup_id')

    if not match_id or not lineup_id:
        return HttpResponse("ERROR: Provide match_id and lineup_id")
    
    qs = MatchLineUp.objects.filter(
        match__id=int(match_id),
        pk=int(lineup_id)
    )

    if not qs.count():
        return HttpResponse("ERROR: No object found to delete")

    error = False

    try:
        qs.delete()
    except:
        error = True

    return HttpResponse("SUCCESS" if not error else "ERROR")


@login_required
def lineup_list(request, match_id):
    match = Match.objects.get(id=int(match_id))
    lineups = match.matchlineup_set.order_by(
        'team', 'player__name', 'player_status'
    )
    context = {
        "lineups": lineups,
        "match": match
    }
    return render_to_response('goalserve/lineuplist.html', context)

    
class JSONStandingsF1View(JSONView):
    def get_context_data(self, **kwargs):
        # agrregate tournaments
        return {}

        
class JSONStandingsDriversView(JSONView):
    def get_context_data(self, **kwargs):
        data = {
            'drivers': [
                {"name": driver.name,
                 "post": driver.post,
                 "team": driver.team.name if driver.team else "",
                 "points": driver.points}
                for driver in sorted(
                    [driver for driver in Driver.objects.filter(post__isnull=False)],
                    key=lambda d:int(d.post or 0)
                )
            ]
        }
        return data

        
class JSONStandingsTeamsView(JSONView):
    def get_context_data(self, **kwargs):
        data = {
            'teams': [
                {"name": team.name,
                 "post": team.post,
                 "points": team.points}
                for team in sorted(
                    [team for team in F1Team.objects.filter(post__isnull=False)],
                    key=lambda d:int(d.post or 0)
                )
            ]
        }
        return data


class JSONStandingsView(JSONView):
    def get_context_data(self, **kwargs):
        return get_tournament_standings()

def response_mimetype(request):
    if "application/json" in request.META['HTTP_ACCEPT']:
        return "application/json"
    return "text/plain"

def get_team_stats(_stats):
    if _stats:
        _stats = _stats[0]
        data = serialize(
            _stats.__dict__,
            exclude=['match_id', 'team_status', 'team_id']
        )
        data['yellowcards'] = _stats.yellowcards
        data['redcards'] = _stats.redcards
        data['goals'] = _stats.goals

        return data
    return {}

def get_team_substitutions(_substitutions):
    if not _substitutions:
        return []

    subs = []

    for sub in _substitutions:
        data = serialize(
            sub.__dict__,
            exclude=['match_id', 'team_status', 'team_id']
        )

        try:
            data['player_in'] = sub.player_in.name
            data['player_in_image'] = sub.player_in.image_url
            data['player_off'] = sub.player_off.name
            data['player_off_image'] = sub.player_off.image_url
        except:
            pass

        subs.append(data)

    return subs


def match(request, match_pk, mode='response'):
    """
    :mode:
       response -  Django response JSON
       json - Dumped JSON object
       python - Pure Python Dictionary
    """
    data = data_match(match_pk)

    def _json_response():
        try:
            response = JSONPResponse(data, {}, response_mimetype(request), request.GET['callback'])
        except:
            response = JSONResponse(data, {}, response_mimetype(request))
        return response

    if mode == 'response':
        response = _json_response()
        response['Content-Disposition'] = 'inline; filename=files.json'
    elif mode == 'sse':
        def _sse_queue():
            redis = Db('goalservematch', match_pk)
            pubsub = redis.object().pubsub()
            pubsub.subscribe(redis.key)
            while True:
                for m in pubsub.listen():
                    if m['type'] == 'message':
                        data = m['data'].decode('utf-8')
                        yield u"data: {}\n\n".format(data)
                yield
                time.sleep(0.5)

        response = StreamingHttpResponse(_sse_queue(),
                                         mimetype='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['Software'] = 'opps-goalserve'
        response.flush()
    elif mode == 'json':
        response = _json_response()
    elif mode == 'python':
        response = data
    else:
        response = "Please specify the mode argument as python, json or response"

    return response


@login_required
def ajax_categories_by_country_name(request, country_name):
    qs = Category.objects.filter(country__name=country_name)
    if qs:
        items = [u"<option value='{item.pk}'>{item.name}</option>".format(item=item)
                 for item in qs]
        response = u"".join(items)
    else:
        response = u"None"
    return HttpResponse(response)


@login_required
def ajax_match_by_category_id(request, category_id):
    qs = Match.objects.filter(
        category__pk=category_id
    ).exclude(
        status__startswith='F'  # remove FT and Full Time matches
    ).order_by(
        '-match_time'
    )

    if qs:
        items = [u"<option value='{item.pk}'>{item.name}</option>".format(item=item)
                 for item in qs]
        response = u"".join(items)
    else:
        response = u"None"
    return HttpResponse(response)


@login_required
def ajax_get_matches(response, country_name, match_id=None):
    task = get_matches.delay(country_name, match_id)
    return HttpResponse(task.task_id)


@login_required
def get_task_status(request, task_id):
    res = AsyncResult(task_id)
    # import ipdb;ipdb.set_trace()
    return HttpResponse(res.status)