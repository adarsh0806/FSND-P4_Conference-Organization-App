#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21
extended by Norbert Stueken on 2015 may 20 (v1.1)
updated by Norbert Stueken after feedback from Helmuth Breitenfellner on 2015
may 26 (v1.2)
"""

# built-in modules
from datetime import datetime
# third-party modules
import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote
from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api import taskqueue
# own modules
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import Session
from models import SessionForm
from models import SessionForms
from models import Speaker
from models import SpeakerForm
from models import TypeOfSession
from models import BooleanMessage
from models import ConflictException
from models import StringMessage
from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE
from utils import getUserId

# authorship information
__authors__ = "Wesley Chun, Norbert Stueken"
__copyright__ = "Copyright 2015"
__credits__ = ["Wesley Chun, Norbert Stueken, Helmuth Breitenfellner at \
Udacity"]
__license__ = "GPL"
__version__ = "1.2"
__maintainer__ = "Norbert Stueken"
__email__ = "wesc+api@google.com (Wesley Chun), norbert.stueken@gmail.com \
(Norbert Stueken)"
__status__ = "Development"

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

DEFAULTS_SESSION = {
    "highlights": ["Default", "Highlight"],
    "location": "Default Location",
    "typeOfSession": TypeOfSession("NOT_SPECIFIED"),
    "date": "1900-01-01",
    "startTime": "10:00",
    "duration": "00:00"
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS = {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
        }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

# container only used to show city and not field for the request in
# API Explorer
CONF_IN_CITY_REQUEST = endpoints.ResourceContainer(
    city=messages.StringField(1)
)

SESSION_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_BY_TYPE_GET_REQUEST = endpoints.ResourceContainer(
    typeOfSession=messages.EnumField(TypeOfSession, 1),
    websafeConferenceKey=messages.StringField(2),
)

SESSION_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1),
)

WISHLIST_POST_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeSessionKey=messages.StringField(1)
)

SESSION_BY_SPK_AND_CONF_GET_REQUEST = endpoints.ResourceContainer(
    SpeakerForm,
    websafeConferenceKey=messages.StringField(1)
)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID,
               ANDROID_CLIENT_ID, IOS_CLIENT_ID], scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v1.2"""


# - - - Session  objects - - - - - - - - - - - - - - - - - -

    def _copySessionToForm(self, sess):
        """Copies relevant fields from a Session to a SessionForm.

        args:
            sess: Session entity.

        returns:
            sf: SessionForm Message.
        """
        # copy relevant fields from Session to SessionForm
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'typeOfSession':
                    setattr(sf, field.name, getattr(TypeOfSession, getattr(
                        sess, field.name)))
                # convert date to date string;
                elif field.name == 'date':
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                # convert startTime to time string;
                elif field.name.endswith('Time'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                # convert startTime to time string;
                elif field.name == 'duration':
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                # convert list of Speaker keys to list of strings:
                elif field.name == 'speakers':
                    setattr(sf, field.name,
                            [str(s.get().name) for s in sess.speakers])
                # just copy other fields
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, sess.key.urlsafe())
            elif field.name == "websafeConfKey":
                setattr(sf, field.name, sess.key.parent().urlsafe())
        sf.check_initialized()
        return sf

    def _createSessionObject(self, request):
        """Creates a Session and returns an altered SessionForm object.

        args:
            request: Combined Container of a SessionForm object and a
                websafeConferenceKey identifying the conference.
        returns:
            sform: Altered SessionForm object with possible filled in default
                values and a websafeKey identifying the session.
        """
        # check if user is logged in
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # convert websafeKey to conference key
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s'
                % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        if not request.name:
            raise endpoints.BadRequestException("Session 'name' field \
                required")

        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in
                request.all_fields()}
        del data['websafeKey']
        del data['websafeConfKey']
        del data['websafeConferenceKey']

        # add default values for those missing (both data model & outbound
        # Message)
        for df in DEFAULTS_SESSION:
            if data[df] in (None, []):
                data[df] = DEFAULTS_SESSION[df]
                setattr(request, df, DEFAULTS_SESSION[df])

        # convert type of session object to string
        if data['typeOfSession']:
            data['typeOfSession'] = str(data['typeOfSession'])
        # convert date from string to Date objects
        if data['date']:
            data['date'] = datetime.strptime(data['date'][:10],
                                             "%Y-%m-%d").date()
        # convert startTime from string to Time objects
        if data['startTime']:
            data['startTime'] = datetime.strptime(data['startTime'][:5],
                                                  "%H:%M").time()
        # convert duration from string to Time objects
        if data['duration']:
            data['duration'] = datetime.strptime(data['duration'][:5],
                                                 "%H:%M").time()
        # convert speakers from a list of strings to a list of Speaker entity
        # keys
        if data['speakers']:
            # check for each provided session speaker if he exists already in
            # the database. If yes, get the key value, if not, create a new
            # speaker with the provided name as key.
            # NOTE: For simplification, it is assumed that a name uniquely
            # identifies a speaker and therefore can be set as id as well.
            sessionSpeakers = []
            for speaker in data['speakers']:
                # get_or_insert(key_name, args) transactionally retrieves an
                # existing entity or creates a new one. This also prevents the
                # risk of duplicate speaker records when multiple sessions with
                # the same speaker are created at the same time.
                # For the key name, the speaker string is formatted in lower
                # case without whitespaces. To be safe, it should also be
                # converted to an ascii string in case of special unicode
                # characters. However, as this is more complicated, its not
                # been done for this exercise.
                session_speaker_key = Speaker.get_or_insert(
                     speaker.lower().strip().replace(" ", "_"),
                     name=speaker).key
                # Add Speaker key to the list of sessionSpeakers.
                sessionSpeakers.append(session_speaker_key)
            # overwrite data['speakers'] with the new created key list.
            data['speakers'] = sessionSpeakers

        # get Conference Key
        c_key = conf.key
        # allocate new Session ID with Conference key as parent
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        # create a key for for the new Session with conference key as parent
        s_key = ndb.Key(Session, s_id, parent=c_key)
        # add key into dictionary
        data['key'] = s_key
        # create Session
        Session(**data).put()
        # get session to copy it back to the form as return
        sess = s_key.get()
        # add task to queue to check the speakers of the conference
        taskqueue.add(params={'c_key_str': c_key.urlsafe()},
                      url='/tasks/check_speakers')
        return self._copySessionToForm(sess)

    def _getConferenceSessions(self, request):
        """ Given a conference, return all its sessions.

        args:
            request: request object containing only a websafeConferenceKey
                which uniquely identifies a conference.
        returns:
            sessions: query result set with all sessions related to the
                provided conference key.
        """
        # convert websafeKey to conference key
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s'
                % request.websafeConferenceKey)
        # get the conference key
        c_key = conf.key
        # create ancestor query for this user
        sessions = Session.query(ancestor=c_key)
        return sessions

    def _getSpeakerKey(self, request):
        """ Returns the key for a requested speaker, when he exists."""

        if not request.name:
            raise endpoints.BadRequestException("Speaker 'name' field \
                required")

        # create a new Speaker.key
        spk_key = Speaker().key
        # query all existing/known speakers
        qryKnownSpeakers = Speaker.query()
        # write the names of the known speakers in a list
        knownSpeakers = []
        for ks in qryKnownSpeakers:
            knownSpeakers.append(ks.name)
        # If speaker doesn't exist, raise an "Not Found"-exception.
        if request.name not in knownSpeakers:
            raise endpoints.NotFoundException(
                'No speaker found with name: %s'
                % request.name)
        # Else return its key.
        # NOTE: For simplification, it is assumed that a name uniquely
        # identifies a speaker.
        else:
            spk_key = Speaker.query(Speaker.name == request.name).get().key
        return spk_key

    @endpoints.method(SESSION_POST_REQUEST, SessionForm,
                      path='conference/{websafeConferenceKey}/sessions',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """ Creates a new session for a conference."""
        return self._createSessionObject(request)

    @endpoints.method(SESSION_GET_REQUEST, SessionForms,
                      path='conference/{websafeConferenceKey}/sessions',
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Given a conference, return all sessions."""
        sessions = self._getConferenceSessions(request)
        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in
                   sessions]
        )

    @endpoints.method(
        SESSION_BY_TYPE_GET_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/sessions/byType',
        http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """ Given a conference, return all sessions of a specified type."""
        sessions = self._getConferenceSessions(request)
        # filter by requested typeOfSession
        sessions = sessions.filter(
            Session.typeOfSession == str(request.typeOfSession))
        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in
                   sessions]
        )

    @endpoints.method(SpeakerForm, SessionForms,
                      path='sessions/bySpeaker',
                      http_method='GET', name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """ Returns all sessions given by a particular speaker."""
        # get key of requested speaker
        spk_key = self._getSpeakerKey(request)
        # create query for all session by provided speaker
        sessions = Session.query(Session.speakers == spk_key)
        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in
                   sessions]
        )

    @endpoints.method(
        SESSION_BY_SPK_AND_CONF_GET_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/sessions/bySpeaker',
        http_method='POST', name='getConferenceSessionsBySpeaker')
    def getConferenceSessionsBySpeaker(self, request):
        """ Returns all conference sessions of a given speaker."""
        # get all sessions of requested conference
        conf_sessions = self._getConferenceSessions(request)
        # get key of requested speaker
        spk_key = self._getSpeakerKey(request)
        # filter conf_sessions for all sessions by provided speaker
        conf_session_by_spk = conf_sessions.filter(Session.speakers == spk_key)
        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in
                   conf_session_by_spk]
        )

    @endpoints.method(WISHLIST_POST_REQUEST, BooleanMessage,
                      path='wishlist',
                      http_method='POST', name='addSessionToWishlist')
    # making the function transactional prevents the risk of losing a session
    # when multiple sessions get added. With @ndb.transaction concurrent writes
    # to the same entity (profile) are not possible. By default, 3 retries are
    # made.
    @ndb.transactional
    def addSessionToWishlist(self, request):
        """ Add a given session to the users Wishlist. """
        onList = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if session exists already on the wishlist
        # given the websafeSessionKey
        wssk = request.websafeSessionKey
        sess = ndb.Key(urlsafe=wssk).get()
        if not sess:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % wssk)

        # check if session is already on the user wishlist
        if wssk in prof.sessionsKeysOnWishlist:
            raise ConflictException(
                "This session is already on your wishlist.")

        # add session to withlist
        prof.sessionsKeysOnWishlist.append(wssk)
        onList = True

        # write added session back to the datastore & return
        prof.put()
        return BooleanMessage(data=onList)

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='wishlist',
                      http_method='GET', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get list of sessions that user has put in his wishlist."""
        prof = self._getProfileFromUser()  # get user profile
        # get sessionsKeysOnWishlist from profile.
        sess_keys = [ndb.Key(urlsafe=wssk) for wssk in
                     prof.sessionsKeysOnWishlist]
        # fetch sessions from datastore.
        # Use of get_multi(array_of_keys) to fetch all keys at once instead of
        # fetching them one by one.
        sessions = ndb.get_multi(sess_keys)

        # return set of SessionForm objects per Session
        return SessionForms(items=[self._copySessionToForm(sess) for sess in
                            sessions])

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='solutionToQueryProblem', http_method='GET',
                      name='solutionToQueryProblem')
    def solutionToQueryProblem(self, request):
        """Solution to the inequality filter limitation to one property."""
        # The following doesn't work as two inequality filters are used:
        # q = Session.query(ndb.AND(
        #     Session.typeOfSession != "Workshop", Session.startTime <= time))

        q = Session.query(ndb.AND(
                          Session.typeOfSession.IN(["NOT_SPECIFIED", "Lecture",
                                                    "Keynote", "Information",
                                                    "Networking"]),
                          Session.startTime <= datetime.strptime(
                            "7:00 pm", "%I:%M %p").time()))

        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in q]
        )


# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning
        ConferenceForm/request.
        """
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field \
                required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in
                request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound
        # Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start
        # date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10],
                                                  "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10],
                                                "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # make Profile Key from user ID
        p_key = ndb.Key(Profile, user_id)
        # allocate new Conference ID with Profile key as parent
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        # make Conference key from ID
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
                      'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email'
                      )
        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in
                request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s'
                % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s'
                % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conference/byUser', http_method='POST',
                      name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # make profile key
        p_key = ndb.Key(Profile, getUserId(user))
        # create ancestor query for this user
        conferences = Conference.query(ancestor=p_key)
        # get the user profile and display name
        prof = p_key.get()
        displayName = getattr(prof, 'displayName')
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, displayName) for conf in
                   conferences]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in
                     f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid \
                    field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous
                # filters
                # disallow the filter if inequality was performed on a
                # different field before
                # track the field on which the inequality operation is
                # performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is \
                        allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences', http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in
                      conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf,
                               names[conf.organizerUserId]) for conf in
                               conferences])

    @endpoints.method(CONF_IN_CITY_REQUEST, ConferenceForms,
                      path='conference/byCity/{city}',
                      http_method='GET', name='getConferencesInCity')
    def getConferencesInCity(self, request):
        """ Returns all conferences in a certain city."""
        # check if city name is given
        if not request.city:
            raise endpoints.BadRequestException("Conference 'city' field \
                required")
        # get all conferences, filter the conference by the requested city and
        # order them by name.
        confsInCity = Conference.query().filter(
            Conference.city == request.city).order(Conference.name)
        # return set of SessionForm objects per Session
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in
                   confsInCity]
        )

    @endpoints.method(CONF_GET_REQUEST, StringMessage,
                      path='conference/featured',
                      http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return featured speakers and their sessions from memcache."""
        # check if conf exists given websafeConferenceKey
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)
        MEMCACHE_CONFERENCE_KEY = "FEATURED:%s" % wsck
        return StringMessage(data=memcache.get(
            MEMCACHE_CONFERENCE_KEY) or "No featured speakers.")

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof,
                            field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if
        non-existent.
        """
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()

        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm, path='profile',
                      http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm, path='profile',
                      http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(
            MEMCACHE_ANNOUNCEMENTS_KEY) or "")


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user profile
        # get conferenceKeysToAttend from profile.
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in
                     prof.conferenceKeysToAttend]
        # fetch conferences from datastore.
        # Use of get_multi(array_of_keys) to fetch all keys at once instead of
        # fetching them one by one.
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in
                      conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf,
                               names[conf.organizerUserId]) for conf in
                               conferences])

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='filterPlayground', http_method='GET',
                      name='filterPlayground')
    def filterPlayground(self, request):
        q = Conference.query()
        # simple filter usage:
        q = q.filter(Conference.city == "London")
        # advanced filter building and usage
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.topics == "Medical Innovations")

        # the first sort property must be the same as the property to which the
        # inequality filter is applied.
        q = q.order(Conference.maxAttendees)
        q = q.filter(Conference.maxAttendees > 10)
        # order by conference name
        q = q.order(Conference.name)
        # filter for June
        q = q.filter(Conference.month == 6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

# registers API
api = endpoints.api_server([ConferenceApi])
