from twilio.rest import Client
from django.conf import settings


def send_sms(phone_number, message):
    """Send an SMS via Twilio. Credentials are read from Django settings / .env"""
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_phone = settings.TWILIO_PHONE_NUMBER

    # Ensure international format with +91 prefix for Indian numbers
    if not phone_number.startswith('+'):
        phone_number = '+91' + phone_number.lstrip('0')

    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        body=message,
        from_=from_phone,
        to=phone_number
    )
    return msg.sid
