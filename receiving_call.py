from flask import Flask, request, Response

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from twilio.request_validator import RequestValidator
import all_access_keys  # Your config file with credentials
import openai
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s [%(levelname)s] %(message)s",  # Define the log format
    handlers=[
        logging.FileHandler("receiving_call.log"),  # Log to a file
        logging.StreamHandler()  # Log to the console
    ]
)


# OpenAI API key
openai.api_key = all_access_keys.OPENAI_API_KEY

# Flask app setup
app = Flask(__name__)
# conversation for multi-turn interactions
conversation_history = {}

app.secret_key = all_access_keys.SECRET_KEY

# Base URL for webhooks
BASE_URL = all_access_keys.BASE_URL

# Twilio credentials
ACCOUNT_SID = all_access_keys.ACCOUNT_SID
AUTH_TOKEN = all_access_keys.AUTH_TOKEN
TWILIO_PHONE_NUMBER = all_access_keys.TWILIO_PHONE_NUMBER

# Initialize the Twilio client
client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Google Cloud credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = all_access_keys.GOOGLE_APPLICATION_CREDENTIALS

# Database setup
DATABASE_URL = all_access_keys.DATABASE_URL
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()

# Database Model
class ResponseData(Base):
    __tablename__ = 'responses'
    id = Column(Integer, primary_key=True)
    call_sid = Column(String, unique=True)
    first_name = Column(String)
    last_name = Column(String)
    age = Column(String)
    residency = Column(String)
    recording_url = Column(String)

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

### Routes ###



@app.route("/voice", methods=["POST"])
def voice():
    """Start the call and ask the first question."""
    logging.info(f"POST data received at /voice: {request.form}")

    vr = VoiceResponse()

    # Ask the first question
    gather = Gather(
        input="speech",
        action=f"{BASE_URL}/process_first_name",
        method="POST",
        timeout=10,
        speech_timeout="auto",
    )
    gather.say("Hello! Please say your first name after the beep.", voice="alice")
    vr.append(gather)

    # Redirect if no input
    vr.redirect(f"{BASE_URL}/voice")

    return Response(str(vr), mimetype="application/xml")

@app.route("/start_gpt_conversation", methods=["POST"])
def start_gpt_conversation():
    """Start a dynamic OpenAI conversation."""
    call_sid = request.form.get("CallSid")
    vr = VoiceResponse()

    # Retrieve all collected data
    db_session = SessionLocal()
    try:
        response_data = db_session.query(ResponseData).filter_by(call_sid=call_sid).first()
        if not response_data:
            vr.say("I couldn't find your information. Please try again later.")
            return Response(str(vr), mimetype="application/xml")

        # Prepare conversation history for GPT
        conversation_history = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"My name is {response_data.first_name} {response_data.last_name}. I am {response_data.age} years old and live in {response_data.residency}."}
        ]

        # Generate GPT response using the updated API syntax
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=conversation_history,
        )

        # Extract GPT reply
        gpt_reply = response['choices'][0]['message']['content']
        logging.info(f"GPT reply: {gpt_reply}")
        logging.debug(f"Conversation history: {conversation_history}")

        # Handle GPT reply
        if not gpt_reply.strip():
            vr.say("I'm sorry, I didn't understand that. Can you please try again?")
        else:
            vr.say(gpt_reply)

    except Exception as e:
        logging.error(f"Error with OpenAI API: {e}")
        vr.say("I'm sorry, I couldn't process your request right now. Please try again later.")
    finally:
        db_session.close()

    return Response(str(vr), mimetype="application/xml")




@app.route("/process_first_name", methods=["POST"])
def process_first_name():
    """Handle the user's first name and ask the next question."""
    call_sid = request.form.get("CallSid")
    first_name = request.form.get("SpeechResult")
    logging.info(f"Received first name: {first_name} for CallSid: {call_sid}")

    response = VoiceResponse()

    if first_name:
        # Save first name to database
        db_session = SessionLocal()
        try:
            response_data = db_session.query(ResponseData).filter_by(call_sid=call_sid).first()
            if not response_data:
                response_data = ResponseData(call_sid=call_sid, first_name=first_name)
                db_session.add(response_data)
            else:
                response_data.first_name = first_name
            db_session.commit()
        except Exception as e:
            logging.error(f"Database error: {e}")
            db_session.rollback()
        finally:
            db_session.close()

        # Ask the next question (last name)
        gather = Gather(
            input="speech",
            action=f"{BASE_URL}/process_last_name",
            method="POST",
            timeout=10,
            speech_timeout="auto",
        )
        gather.say(f"Thank you, {first_name}. Please say your last name.", voice="alice")
        response.append(gather)
    else:
        # If no input, redirect back to ask again
        response.say("Sorry, I didn't catch that. Please say your first name again.", voice="alice")
        response.redirect(f"{BASE_URL}/voice")

    return Response(str(response), mimetype="application/xml")




@app.route("/process_last_name", methods=["POST"])
def process_last_name():
    call_sid = request.form.get("CallSid")
    last_name = request.form.get("SpeechResult")
    print(f"DEBUG: Received /process_last_name for CallSid={call_sid}, LastName={last_name}")

    response = VoiceResponse()

    if last_name:
        # Save last name to database
        db_session = SessionLocal()
        try:
            response_data = db_session.query(ResponseData).filter_by(call_sid=call_sid).first()
            if response_data:
                response_data.last_name = last_name
                db_session.commit()
        except Exception as e:
            print(f"Database error: {e}")
            db_session.rollback()
        finally:
            db_session.close()

        # Proceed to the next question
        gather = Gather(
            input="speech",
            action=f"{BASE_URL}/process_age",
            method="POST",
            timeout=10,
            speech_timeout="auto",
        )
        gather.say(f"Thank you, {last_name}. Please say your age.", voice="alice")
        response.append(gather)
    else:
        response.say("Sorry, I didn't catch that. Please say your last name again.", voice="alice")
        response.redirect(f"{BASE_URL}/process_last_name")

    return Response(str(response), mimetype="application/xml")

@app.route("/process_age", methods=["POST"])
def process_age():
    call_sid = request.form.get("CallSid")
    age = request.form.get("SpeechResult")
    logging.debug(f"Received /process_age for CallSid={call_sid}, Age={age}")

    response = VoiceResponse()

    if age:
        # Save age to database
        db_session = SessionLocal()
        try:
            response_data = db_session.query(ResponseData).filter_by(call_sid=call_sid).first()
            if response_data:
                response_data.age = age
                db_session.commit()
                print(f"DEBUG: Age saved for CallSid={call_sid}: {age}")
            else:
                print(f"ERROR: No record found for CallSid={call_sid}")
                response.say("An error occurred. Please start over.", voice="alice")
                response.redirect(f"{BASE_URL}/voice")
                return Response(str(response), mimetype="application/xml")
        except Exception as e:
            print(f"Database error: {e}")
            db_session.rollback()
        finally:
            db_session.close()

        # Proceed to the next step
        gather = Gather(
            input="speech",
            action=f"{BASE_URL}/process_residency",
            method="POST",
            timeout=10,
            speech_timeout="auto",
        )
        gather.say("Thank you. Please state your residency.", voice="alice")
        response.append(gather)
    else:
        print(f"DEBUG: Age input not received for CallSid={call_sid}")
        response.say("Sorry, I didn't catch that. Please say your age again.", voice="alice")
        response.redirect(f"{BASE_URL}/process_age")

    return Response(str(response), mimetype="application/xml")

@app.route("/process_residency", methods=["POST"])
def process_residency():
    call_sid = request.form.get("CallSid")
    residency = request.form.get("SpeechResult")
    logging.debug(f"DEBUG: Received /process_residency for CallSid={call_sid}, Residency={residency}")

    response = VoiceResponse()

    # Validate required inputs
    if not call_sid or not residency:
        logging.warning("Missing CallSid or SpeechResult in /process_residency.")
        response.say("We encountered an issue. Please try again.", voice="alice")
        response.redirect(f"{BASE_URL}/voice")
        return Response(str(response), mimetype="application/xml")

    db_session = SessionLocal()
    try:
        # Save residency in the database
        response_data = db_session.query(ResponseData).filter_by(call_sid=call_sid).first()
        if response_data:
            response_data.residency = residency
            db_session.commit()
        else:
            logging.warning(f"No record found for CallSid={call_sid}.")
    except Exception as e:
        logging.error(f"Database error for CallSid={call_sid}: {e}")
        db_session.rollback()
    finally:
        db_session.close()

    # Thank the caller and end the call
    response.redirect(f"{BASE_URL}/start_gpt_conversation")
    return Response(str(response), mimetype="application/xml")



@app.route("/handle-recording", methods=["POST"])
def handle_recording():
    """Handle the recording completion and save the recording URL."""
    recording_url = request.form.get("RecordingUrl")  # URL of the recording from Twilio
    call_sid = request.form.get("CallSid")  # Unique Call SID from Twilio

    if recording_url and call_sid:
        # Save to the database
        db_session = SessionLocal()
        try:
            # Check if the record for this CallSid exists
            response_data = db_session.query(ResponseData).filter_by(call_sid=call_sid).first()
            if not response_data:
                # Create a new record if it doesn't exist
                response_data = ResponseData(call_sid=call_sid, recording_url=recording_url)
                db_session.add(response_data)
            else:
                # Update the existing record with the new URL
                response_data.recording_url = recording_url
            db_session.commit()
            logging.info(f"Recording URL saved to database for CallSid={call_sid}: {recording_url}")
        except Exception as e:
            logging.error(f"Database error for CallSid={call_sid}: {e}")
            db_session.rollback()
        finally:
            db_session.close()

        # Save to the text file
        try:
            with open("recording_urls.txt", "a") as file:
                file.write(recording_url + "\n")
            logging.info(f"Recording URL appended to recording_urls.txt: {recording_url}")
        except Exception as e:
            logging.error(f"Error writing to recording_urls.txt for CallSid={call_sid}: {e}")

    else:
        logging.warning("Missing CallSid or RecordingUrl in webhook payload.")

    return Response("", status=200)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)