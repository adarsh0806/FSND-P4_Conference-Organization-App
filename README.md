Conference Organization Application Using Googles App Engine.

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Setup Instructions
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

## Explanation of design choices for the Sessions and Speaker implementations as added features of the App.
The Session kind has been designed with the following attributes:
 	- name: StringProperty and the only required field.
 	- highlights: Repeated StringProperty as there can be multiple highlights per Session.
 	- speakers: Repeated KeyProperty of kind Speakers, as there can be multiple Speakers per Session as well.
 	- duration, startTime and date: TimeProperty respectively DateProperty attributes.
 	- typeOfSession and location: StringProperties.
 As a session is created as a child of a given conference which key is included in the key of the session, it doesn't need to hold a separate conference attribute as in a relational database. A session object is created using the SessionForm Message class, basically consisting of string fields. Only typeOfSession is implemented as an EnumField as there are limited values to chose from. To output multiple SessionForm objects, the SessionsForms Message class is used.

 The Speaker kind is a simple class containing only the name of the speaker as required attribute. To simplify the use of the API Explorer in this project, the Speaker name is used as a unique identifier and form input and not an unique ID as it should be done in a professional project. The SpeakerForm Message class is used to input a speaker for the getSessionsBySpeaker-Method.

 To make use of the new Session and Speaker kinds, the following endpoints and private methods have been implemented. The private methods are used by the endpoints methods, but are not publicly available through the API.
 - createSession(): Creates a new session for a conference.
 - getConferenceSessions(): Given a conference, return all sessions.
 - getConferenceSessionsByType(): Given a conference, return all sessions of a specified type.
 - getSessionsBySpeaker(): Returns all sessions given by a particular speaker.
 - _copySessionToForm(): Copies relevant fields from a Session to a SessionForm. Implemented as a separate mehthod since used by multiple methods (_createSessionObject, getConferenceSessions and getConferenceSessionsByType) to limit redundancy.
 - _createSessionObject(): Creates a Session and returns an altered SessionForm object. In order to create a session, you need to be the creator of the conference and logged in respectively.
 - _getConferenceSessions(): Given a conference, return all its sessions. Implemented as separate method as used by multiple endpoints methods (getConferenceSessions and getConferenceSessionsByType) to limit redundancy.



[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
