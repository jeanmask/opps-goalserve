#coding: utf-8

import urllib
import datetime
from .xml2dict import parse
from .countries import COUNTRIES
from .commentaries import COMMENTARIES
from .standings import STANDINGS
from .models import Country, Category, Match, Team, Stadium, Player, MatchLineUp, MatchStats, \
                    MatchSubstitutions, MatchCommentary, MatchEvent, MatchStandings

DOMAIN = 'http://www.goalserve.com'

"""
Formula 1:

/getfeed/{gid}/f1/drivers
/getfeed/{gid}/f1/f1-results
/getfeed/{gid}/f1/f1-shedule
/getfeed/{gid}/f1/live
/getfeed/{gid}/f1/teams
"""

URLS = {
    'matches': ['/getfeed/{gid}/soccernew/{country}',
               '/getfeed/{gid}/soccernew/{country}_shedule'],
    'standings': '/getfeed/{gid}/standings/{xml}',
    'comments': '/getfeed/{gid}/commentaries/{xml}',
    'team': '/getfeed/{gid}/soccerstats/team/{team_id}',
    'player': '/getfeed/{gid}/soccerstats/player/{player_id}'
}


class Crawler(object):
    def __init__(self, gid, update_all_players=False, update_all_teams=False):
        self.gid = gid
        self.update_all_players = update_all_players
        self.update_all_teams = update_all_teams

    def load_countries(self):
        for country in COUNTRIES:
            # print
            Country.objects.get_or_create(
                name=country.lower()
            )

    def get(self, url):
        print "getting", url
        try:
            return parse(
                urllib.urlopen(
                    DOMAIN + url
                ).read()
            )
        except Exception as e:
            print  e.message
            return None

    def parse_date(self, date, time=None, format=None):
        print "parsing date", date, format
        if not date:
            return


        dt = '{date} {time}'.format(date=date, time=time) if time else date
        parsed = datetime.datetime.strptime(
            dt,
            format or '%d.%m.%Y %H:%M'
        )
        print parsed
        return parsed

    def get_country_by_name(self, name):
        print "getting country by", name
        _country, created = Country.objects.get_or_create(name=name.lower())
        return _country

    def get_stadium(self, data, country=None):
        print "getting stadium"
        _stadium, created = Stadium.objects.get_or_create(
            g_id=data['venue_id']
        )

        try:
            _stadium.country=country or self.get_country_by_name(data['country'])
            _stadium.name=data['venue_name']
            _stadium.surface = data.get('venue_surface')
            _stadium.capacity = data.get('venue_capacity') or None
            _stadium.image_base = data.get('venue_image')
            _stadium.save()
        except Exception as e:
            print  e.message

        return _stadium

    def get_team(self, team, get_players=True):
        print "getting team"
        # OrderedDict([(u'@name', u'Santos'), (u'@goals', u'?'), (u'@id', u'7560')]))
        _team, created = Team.objects.get_or_create(
            g_id=team['@id']
        )

        if created or self.update_all_teams:
            # http://www.goalserve.com/getfeed/c93ce5a5b570433b8a7d96b3c53f119d/soccerstats/team/9260
            data = self.get(
                URLS.get('team').format(gid=self.gid, team_id=team['@id'])
            )

            _team.name=team['@name']

            try:
                team = data['teams']['team']
                _team.full_name = team.get('fullname')
                _team.country = self.get_country_by_name(team.get('country'))
                _team.stadium = self.get_stadium(team, _team.country)
                _team.founded = team.get('founded')
                _team.coach = team.get('coach', {}).get('@name')
                _team.image_base = team.get('image')
                _team.save()
            except Exception as e:
                print  e.message

            if not team.get('@is_national') and get_players:  # dont overrride player for worldcup team
                for player in data['teams']['team']['squad']['player']:
                    self.get_player(player, _team)

        return _team

    def get_player(self, player, _team):
        print "getting player"
        _player, created = Player.objects.get_or_create(
                g_id=player['@id'],
                g_player_id=player['@id'],
        )

        if not _player:
            return

        if created or self.update_all_players:
            _player.number = player.get('@number', _player.number)
            _player.name=player['@name']
            _player.team=_team

            # http://www.goalserve.com/getfeed/c93ce5a5b570433b8a7d96b3c53f119d/soccerstats/player/193
            data = self.get(
                URLS.get('player').format(gid=self.gid, player_id=player['@id'])
            )

            if not data:
                return

            try:
                player = data['players']['player']
                _player.birthdate=self.parse_date(player.get('birthdate'), format='%m/%d/%Y')
                _player.age=player.get('age') or None
                _player.nationality=player.get('nationality')
                _player.birthplace=player.get('birthplace')
                _player.position=player.get('position')
                _player.weight=player.get('weight')
                _player.height=player.get('height')
                _player.image_base=player.get('image')
                _player.save()
            except Exception as e:
                print  e.message

        print _player
        return _player

    def get_commentaries(self, _match, country_name=None):
        print "getting commentaries"
        xmls = COMMENTARIES.get(country_name or _match.category.country.name, [])
        for xml in xmls:
            data = self.get(
                URLS.get('comments').format(gid=self.gid, xml=xml)
            )

            if not data:
                return

            try:
                matches = data['commentaries']['tournament']['match']
            except KeyError:
                continue

            for match in matches:
                if match.get('@static_id') != _match.g_static_id:
                    continue

                try:
                    _match.status = match.get('@status')
                    _match.match_time=self.parse_date(
                                   match.get('@formatted_date'),
                                   match.get('@time')
                    )

                    try:
                        stadium_name, stadium_city, stadium_country = \
                            match['matchinfo']['stadium']['@name'].split(',')

                        try:
                            _match.stadium = Stadium.objects.get(
                                name__icontains=stadium_name.strip(),
                                country=self.get_country_by_name(stadium_country.strip().lower())
                            )
                        except Stadium.DoesNotExist:
                            _match.stadium, created = Stadium.objects.get_or_create(
                                name=stadium_name.strip(),
                                country=self.get_country_by_name(stadium_country.strip().lower())
                            )

                    except:
                        pass


                    _match.save()
                except Exception as e:
                    print  e.message

                else:
                    self.get_match_lineup(_match, match.get('teams'))
                    self.get_match_lineup(_match, match.get('substitutes'),
                                          player_status='substitute')
                    self.get_match_stats(_match, match.get('stats'))
                    self.get_match_substitutions(_match, match.get('substitutions'))
                    self.get_match_commentaries(_match, match.get('commentaries'))

    def get_match_commentaries(self, _match, commentaries):
        print 'getting commentaries'
        if not commentaries:
            return

        for comment in commentaries['comment']:
            _matchcommentary, created = MatchCommentary.objects.get_or_create(
               g_id=comment.get('@id'),
               match=_match
            )
            if created:
                _matchcommentary.important = True if comment.get('@important') == 'True' else False
                _matchcommentary.is_goal = True if comment.get('@isgoal') == 'True' else False
                _matchcommentary.minute = comment.get('@minute', '').replace("'", "") or None
                _matchcommentary.comment = comment.get('@comment')
                _matchcommentary.save()


    def get_match_substitutions(self, _match, substitutions):
        print "getting substitutions"
        if not _match or not substitutions:
            return

        for team_status in ['localteam', 'visitorteam']:
            substitution = substitutions[team_status]
            _team = getattr(_match, team_status, None)

            data = substitution.get('substitution')
            if not data:
                return

            for item in data:
                try:
                    _matchsubs, created = MatchSubstitutions.objects.get_or_create(
                        team=_team,
                        match=_match,
                        team_status=team_status,
                        player_in=self.get_player_by_id(item.get('@on_id')),
                        player_off=self.get_player_by_id(item.get('@off_id')),
                        minute=item.get('@minute')
                    )
                    _matchsubs.save()
                except Exception as e:
                    print e.message


    def get_player_by_id(self, g_id):
        if not g_id:
            return

        try:
            _player = Player.objects.get(g_id=g_id)
        except Player.DoesNotExist:
            _player = None

        if not _player:
            data = self.get(
                URLS.get('player').format(gid=self.gid, player_id=g_id)
            )
            if not data:
                return

            try:
                player = data['players']['player']
                _player = Player()
                _player.name=player.get('name')
                _player.g_id=g_id
                _player.g_player_id=g_id
                _player.birthdate=self.parse_date(player.get('birthdate'), format='%m/%d/%Y')
                _player.age=player.get('age') or None
                _player.nationality=player.get('nationality')
                _player.birthplace=player.get('birthplace')
                _player.position=player.get('position')
                _player.weight=player.get('weight')
                _player.height=player.get('height')
                _player.image_base=player.get('image')
                _player.save()
            except Exception as e:
                print  e.message

        return _player


    def get_match_stats(self, _match, stats):
        print "getting match stats"
        if not _match or not stats:
            return

        for team_status in ['localteam', 'visitorteam']:
            stat = stats.get(team_status)
            _team = getattr(_match, team_status, None)

            _stat, created = MatchStats.objects.get_or_create(
                match=_match,
                team=_team,
                team_status=team_status
            )

            try:
                _stat.shots = stat.get('shots', {}).get('@total', None)
                _stat.shots_on_goal = stat.get('shots', {}).get('@ongoal', None)
                _stat.fouls = stat.get('fouls', {}).get('@total', None)
                _stat.corners = stat.get('corners', {}).get('@total', None)
                _stat.offsides = stat.get('offsides', {}).get('@total', None)
                _stat.possesiontime = stat.get('possestiontime', {}).get('@total', None)
                _stat.saves = stat.get('saves', {}).get('@total', None)
                _stat.save()
            except Exception as e:
                print e.message

    def get_match_lineup(self, _match, teams, player_status='player'):
        print "getting linepup"

        if not _match or not teams:
            return

        for team_status in ['localteam', 'visitorteam']:
            team = teams[team_status]
            _team = getattr(_match, team_status, None)
            for player in team['player']:

                try:
                    _player =  Player.objects.get(g_id=player['@id'])
                except:
                    _player = self.get_player(player, _team)

                if not _player:
                    return

                _lineup, created = MatchLineUp.objects.get_or_create(
                    match=_match,
                    player=_player,
                    team=_team,
                    team_status=team_status,
                )

                _lineup.player_status = player_status

                _lineup.player_number=player.get('@number', _player.number) or None
                _lineup.player_position=player.get('@pos', _player.position)
                _lineup.save()

                print  _lineup


    def get_match_events(self, _match, events):
        print "getting events"
        if not _match or not events:
            return

        for event in events.get('event', []):
            _matchevent, created = MatchEvent.objects.get_or_create(
                g_id=event.get('@eventid'),
                g_event_id=event.get('@eventid'),
                match=_match
            )

            _matchevent.event_type = event.get('@type')
            _matchevent.minute = event.get('@minute', '').replace("'", "") or None
            _matchevent.team_status = event.get('@team')
            _matchevent.result = event.get('@result')
            _matchevent.player = self.get_player_by_id(event.get('@playerId'))
            _matchevent.team = getattr(_match, event.get('@team', 'x'), None)
            _matchevent.save()


    def get_matches(self, countries=COUNTRIES, match_id=None):
        print "getting matches"
        for country in countries:
            _country, created = Country.objects.get_or_create(
                name=country.lower()
            )

            for xml_url in URLS.get('matches'):
                url = xml_url.format(
                    gid=self.gid, country=country
                )

                data = self.get(url)

                for category in data['scores']['category']:
                    _category, created = Category.objects.get_or_create(
                        g_id=category['@id']
                    )

                    if created:
                        _category.name=category['@name']
                        _category.country=_country
                        _category.save()

                    print "category", _category.name, created

                    # import ipdb; ipdb.set_trace()
                    for match in category['matches']['match']:

                        # TODO: catch this bug
                        if isinstance(match, (unicode, str)):
                            continue

                        if not match.get('@static_id'):
                            print  "Match not ready"
                            continue

                        if match_id:
                            if isinstance(match_id, list):
                                if not match.get('@static_id') in [str(item) for item in match_id]:
                                    continue
                            else:
                                if str(match_id) != match.get('@static_id'):
                                    continue

                        _match, created = Match.objects.get_or_create(
                            category=_category,
                            g_static_id=match['@static_id'],
                        )

                        print "getting", _match.g_static_id

                        try:

                            localteam = match.get('localteam')
                            visitorteam = match.get('visitorteam')

                            _match.status=match.get('@status')
                            _match.match_time=self.parse_date(
                                           match.get('@formatted_date'),
                                           match.get('@time')
                            )
                            _match.localteam=self.get_team(localteam)
                            _match.visitorteam=self.get_team(visitorteam)
                            _match.ht_result=match.get('ht', {}).get('@score')
                            _match.g_id=match.get('@id')
                            _match.g_fix_id=match.get('@fix_id')

                            try:
                                localteam_goals = int(localteam.get('@goals') or 0)
                                visitorteam_goals = int(visitorteam.get('@goals') or 0)

                                if localteam_goals > (_match.localteam_goals or 0):
                                    _match.localteam_goals = localteam_goals

                                if visitorteam_goals > (_match.visitorteam_goals or 0):
                                    _match.visitorteam_goals = visitorteam_goals

                            except:
                                pass


                            _match.save()


                        except Exception as e:
                            print  e.message
                        else:
                            print  "Match recorded", _match.pk

                        if _match.g_static_id:
                            self.get_match_events(_match,  match.get('events'))
                            self.get_commentaries(_match, country)

    def get_category_by_id(self, g_id, tournament=None, country=None):
        try:
            return Category.objects.get(g_id=g_id)
        except:
            if not tournament:
                return

            _category = Category.objects.create(
                country=country,
                name=tournament.get('@league'),
                g_id=g_id
            )
            return _category

    def get_standings(self, country='brazil'):
        print "get_standings"
        for xml in [item for item in STANDINGS if item.startswith(country)]:

            data = self.get(
                URLS.get('standings').format(gid=self.gid, xml=xml)
            )

            if not data:
                print "not data"
                continue

            standings = data.get('standings')
            _country = self.get_country_by_name(standings.get('@country'))
            timestamp = standings.get('@timestamp')
            tournaments = standings.get('tournament', {})

            if not isinstance(tournaments, list):
                tournaments = [tournaments]

            for tournament in tournaments:

                _category = self.get_category_by_id(tournament.get('@id'), tournament, _country)

                if not _category:
                    continue

                for team in tournament.get('team', []):
                    _team = self.get_team(team, get_players=False)
                    _matchstandings, created = MatchStandings.objects.get_or_create(
                        season=tournament.get('@season'),
                        round=tournament.get('@round'),
                        category=_category,
                        team=_team,
                        country=_country
                    )

                    _matchstandings.position = team.get('@position')
                    _matchstandings.status = team.get('@status')
                    _matchstandings.recent_form = team.get('@recent_form')
                    _matchstandings.total_gd = team.get('total', {}).get('@gd')
                    _matchstandings.total_p = team.get('total', {}).get('@p')

                    _matchstandings.overall_gp = team.get('overall', {}).get('@gp')
                    _matchstandings.overall_w = team.get('overall', {}).get('@w')
                    _matchstandings.overall_l = team.get('overall', {}).get('@l')
                    _matchstandings.overall_gs = team.get('overall', {}).get('@gs')
                    _matchstandings.overall_ga = team.get('overall', {}).get('@ga')


                    _matchstandings.description = team.get('description', {}).get('@value')


                    _matchstandings.timestamp = timestamp
                    _matchstandings.save()

                    print _matchstandings, created