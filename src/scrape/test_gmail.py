from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes for Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Authenticate
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

# Build the service
service = build('gmail', 'v1', credentials=creds)

# Example: List first 10 messages
results = service.users().messages().list(userId='me', maxResults=10).execute()
messages = results.get('messages', [])
for msg in messages:
    print(msg['id'])

import pickle

with open('token.pickle', 'wb') as token_file:
    pickle.dump(creds, token_file)