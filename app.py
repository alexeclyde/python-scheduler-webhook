import os
import flask
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = flask.Flask(__name__)
# It's crucial to set a secret key for session management
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-key-for-dev")

# --- CONFIGURATION ---
# Use the web credentials for the web application
CLIENT_SECRETS_FILE = "web_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
MY_EMAIL = "alex@extech.net"


# --- WEB ROUTES ---

@app.route('/')
def index():
    return "Calendar Booking Webhook is running."


@app.route('/book')
def book():
    """
    Initiates the booking process when a client clicks the link.
    It saves the booking details in the session and redirects to Google for auth.
    """
    # Store booking info in the session before redirecting
    flask.session['event_id'] = flask.request.args.get('eventId')
    flask.session['client_email'] = flask.request.args.get('clientEmail')

    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    # The redirect_uri must match one of the "Authorized redirect URIs" in your GCP credentials
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    flask.session['state'] = state

    return flask.redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
    """
    Handles the callback from Google after authentication.
    """
    state = flask.session['state']
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials

    # Retrieve booking info from session
    event_id = flask.session.get('event_id')
    client_email = flask.session.get('client_email')

    if not event_id or not client_email:
        return "Error: Booking information was lost. Please try again.", 400

    try:
        calendar_service = build('calendar', 'v3', credentials=credentials)

        # 1. Get the original "O4C" event to retrieve its time
        original_event = calendar_service.events().get(calendarId='primary', eventId=event_id).execute()

        start_time = original_event['start']
        end_time = original_event['end']

        # 2. Update the event to be the actual meeting
        updated_event_body = {
            'summary': f'Call with {client_email}',
            'description': 'This call was booked via the automated scheduling assistant.',
            'start': start_time,
            'end': end_time,
            'attendees': [
                {'email': MY_EMAIL},
                {'email': client_email},
            ],
            'reminders': {
                'useDefault': True,
            },
        }

        # Use patch to update only specified fields
        calendar_service.events().patch(
            calendarId='primary',
            eventId=event_id,
            body=updated_event_body,
            sendUpdates='all'  # Notifies attendees of the change
        ).execute()

        return "<h1>Booking Confirmed!</h1><p>The meeting has been added to the calendar and an invitation has been sent.</p>", 200

    except HttpError as error:
        print(f"An error occurred: {error}")
        return f"An error occurred while booking the meeting: {error}", 500
    except Exception as e:
        print(f"A general error occurred: {e}")
        return "An unexpected error occurred.", 500


if __name__ == '__main__':
    # For local development, you can run this. For production, use a WSGI server.
    # Make sure to run on a port that is accessible.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)
