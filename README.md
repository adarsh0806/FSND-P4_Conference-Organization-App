# Cloud-based API server for a Conference Organization Application using Googles App Engine.
The API supports user authentication, user profiles, conference information and various manners in which to query the data.

# Products
- [App Engine][1]

# Language
- [Python][2]

# APIs
- [Google Cloud Endpoints][3]

# Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
2. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
3. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
4. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
5. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting
   your local server's address (by default [localhost:8080][5].)
6. Generate your client library(ies) with [the endpoints tool][6].
7. Deploy your application by typing 'appcfg.py update DIR'. When successful, you can access your application
   by visiting 'https://APPID.appspot.com'.

# Testing Instructions
To access the conference application, visit 'https://conference-api.appspot.com'.
As the added endpoints methods are only usable in the API explorer yet, visit 'https://conference-api.appspot.com/_ah/api/explorer/', click on the conference API and chose the method you want to test. To get a valid websafeConferenceKey, copy it from the url on any conference detail page. To get a valid sessionConferenceKey, copy the websafeKey from the response of the getConferenceSessions-method. 

# Task 1 & 2: Explanation of the design choices for Sessions, Speaker and Wishlist.
The Session kind has been designed with the following properties:
- name: StringProperty and the only required field.
- highlights: Repeated StringProperty as there can be multiple highlights per Session.
- speakers: Repeated KeyProperty of kind Speakers, as there can be multiple Speakers per Session as well.
- duration, startTime and date: TimeProperty respectively DateProperty properties.
- typeOfSession and location: StringProperties.
 As a session is created as a child of a given conference which key is included in the key of the session, it doesn't need to hold a separate conference property as in a relational database. 

 A session object is created using the SessionForm Message class, basically consisting of string fields. Only typeOfSession is implemented as an EnumField as there are limited values to chose from. When an existing Session entity is requested, the message field 'websafeKey' contains an urlsafe string which can be easily converted back to the original key to uniquely identify the session.

 To output multiple SessionForm objects, the SessionsForms Message class is used.

 The Speaker kind is a simple class containing only the name of the speaker as required property. To simplify the use of the API Explorer in this project, the Speaker name is used as a unique identifier and form input and not an unique ID as it should be done in a professional project.

 The SpeakerForm Message class is used to input a speaker for the getSessionsBySpeaker-Method.

 To make use of the new Session and Speaker kinds, the following endpoints and private methods have been implemented. The private methods are used by the endpoints methods, but are not publicly available through the API.
 - createSession: Creates a new session for a conference.
 - getConferenceSessions: Given a conference, return all sessions.
 - getConferenceSessionsByType: Given a conference, return all sessions of a specified type.
 - getSessionsBySpeaker: Returns all sessions given by a particular speaker.
 - _copySessionToForm: Copies relevant fields from a Session to a SessionForm. Implemented as a separate mehthod since used by multiple methods (_createSessionObject, getConferenceSessions and getConferenceSessionsByType) to limit redundancy.
 - _createSessionObject: Creates a Session and returns an altered SessionForm object. In order to create a session, you need to be the creator of the conference and logged in respectively.
 - _getConferenceSessions: Given a conference, return all its sessions. Implemented as separate method as used by multiple endpoints methods (getConferenceSessions and getConferenceSessionsByType) to limit redundancy.
 - _getSpeakerKey: Returns the key for a requested speaker, when he exists. Implemented as separate method as used by multiple endpoints mehtods (getSessionsBySpeaker and getConferenceSessionsBySpeaker (see additional queries/methods below)).

As the wishlist is only a list of session keys, it doesn't need to be an own kind and can be attached to the user profile as an additional property. Furthermore, the wishlist is open to all conferences and not only the ones which the user is registered to attend. For me, this makes more sense as I could decgide to register for a conference based on the sessions in my wishlist. 

The following methods have been implemented for the wishlist to work:
- addSessionToWishlist: To add a session to the wishlist, the websafeKey of the session (probably retrieved out of a hidden form element on the conference details page) is used as the input argument. Furthermore, the method is implemented similar to the _conferenceRegistration method. The method is transactional to prevent the risk of losing a session when multiple calls are made concurrently.
- getSessionsInWishlist: Retrieves a list of sessions which have been put on the users wishlist across all conferences. This method is implemented very similar to the method 'getConferencesToAttend'.

# Task 3: Additional added queries in endpoint methods
- getConferenceSessionsBySpeaker: This method queries all sessions of a conference and filters it by a given speaker. This can be useful for larger conferences.
- getConferencesInCity: This method queries all conferences in a certain city.

# Task 3: Solving a query related problem
Question: Let’s say that you don't like workshops and you don't like sessions after 7 pm. How would you handle a query for all non-workshop sessions before 7 pm? What is the problem for implementing this query? What ways to solve it did you think of?

Answer: The query would need to filter using two inequality filterss. First, all sessions '!=' Workshop, second, all sessions <= 7 pm. However, using inequalities for multiple properties is [disallowed in Datastore][7].

Proposed Solutions:
1. Use only one inequality filter for time and then filter for all type of sessions which
   are liked using the IN operator on a limited set of the remaining five session types.
2. Use two queries with one inequality filter each and combine the results.
3. Use only one inequality filter for time and filter out the other property in memory.

Implemented Solution:
As the amount of possible typeOfSession values is very limited, I decided to implemt the first proposed solution. Furthermore, it uses only available Datastore operators and is probably the most straightforward solution as well:

	q = Session.query(ndb.AND(
	                  Session.typeOfSession.IN(["NOT_SPECIFIED", "Lecture",
	                                            "Keynote", "Information",
	                                            "Networking"]),
	                  Session.startTime <= datetime.strptime(
	                    "7:00 pm", "%I:%M %p").time()))

The whole endpoints method is implemented as 'solutionToQueryProblem'.

# Task 4: Add a Task
For this a new task is added to the default taskqueue after a session is created. In the executed method 'CheckSpeakers' of the main.py module, all sessions of the same conference are checked if a speaker holds more than one session at the conference. If this is the case, the speaker gets marked as featured and a new Memcache entry is created (or the existing one is overridden) listing all featured speakers and their session on this conference.

The endpoints method 'getFeaturedSpeaker' takes in a websafeConferenceKey as an argument and returns the respective Memcache entry with the featured speakers and sessions.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
[7]: https://cloud.google.com/appengine/docs/python/ndb/queries
