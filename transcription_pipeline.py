import os
import requests
import subprocess
import wave
import logging
from google.cloud import speech, storage
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
import all_access_keys

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        logging.StreamHandler()          # Log to the console
    ]
)

ACCOUNT_SID = all_access_keys.ACCOUNT_SID
AUTH_TOKEN = all_access_keys.AUTH_TOKEN
TWILIO_PHONE_NUMBER = all_access_keys.TWILIO_PHONE_NUMBER


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = all_access_keys.GOOGLE_APPLICATION_CREDENTIALS



# Google Cloud and database setup
DATABASE_URL = "sqlite:///transcriptions.db"  # Replace with your DB connection string
GCS_BUCKET_NAME = 'audiofilesprankcall'

# Database setup
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


# Database Model
class ResponseData(Base):
    __tablename__ = 'responses'
    id = Column(Integer, primary_key=True, index=True)
    call_sid = Column(String, unique=True, index=True)
    recording_url = Column(String, nullable=True)
    transcription = Column(String, nullable=True)


Base.metadata.create_all(engine)  # Create tables if they don't exist


# Helper Functions
def read_recording_urls(file_path="recording_urls.txt"):
    try:
        with open(file_path, "r") as file:
            return [line.strip() for line in file.readlines()]
    except FileNotFoundError:
        logging.warning(f"File not found: {file_path}")
        return []


def get_unprocessed_recordings():
    """Fetch unprocessed recording URLs from the database."""
    db_session = SessionLocal()
    try:
        recordings = db_session.query(ResponseData).filter(ResponseData.transcription == None).all()
        return recordings
    except Exception as e:
        logging.error(f"Error fetching recordings from database: {e}")
        return []
    finally:
        db_session.close()


def download_recording(recording_url, filename="recording.wav"):
    try:
        response = requests.get(recording_url, stream=True)
        response.raise_for_status()
        with open(filename, "wb") as audio_file:
            for chunk in response.iter_content(chunk_size=4096):
                audio_file.write(chunk)
        logging.info(f"Recording saved as {filename}")
        return filename
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download recording: {e}")
        return None


def is_valid_wav(file_path):
    try:
        with wave.open(file_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            return sample_rate == 16000 and channels == 1
    except wave.Error as e:
        logging.error(f"Error checking WAV file: {e}")
        return False


def convert_to_wav(input_file, output_file="converted_recording.wav"):
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_file,
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", output_file
        ], check=True)
        logging.info(f"Converted {input_file} to {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        logging.error(f"Error converting file: {e}")
        return None


def upload_to_gcs(file_path, destination_blob_name):
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_path)
        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{destination_blob_name}"
        logging.info(f"Uploaded {file_path} to {gcs_uri}")
        return gcs_uri
    except Exception as e:
        logging.error(f"Error uploading to GCS: {e}")
        return None


from google.cloud import speech

def transcribe_audio_with_diarization(file_path):
    try:
        client = speech.SpeechClient()

        # Get audio duration
        with wave.open(file_path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / float(rate)
            logging.info(f"Audio duration: {duration} seconds")

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            diarization_config=speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=1,
                max_speaker_count=2  # Adjust based on expected number of speakers
            )
        )

        if duration <= 60:
            with open(file_path, "rb") as audio_file:
                content = audio_file.read()
            audio = speech.RecognitionAudio(content=content)
            response = client.recognize(config=config, audio=audio)
        else:
            destination_blob_name = os.path.basename(file_path)
            gcs_uri = upload_to_gcs(file_path, destination_blob_name)
            if not gcs_uri:
                return None
            audio = speech.RecognitionAudio(uri=gcs_uri)
            operation = client.long_running_recognize(config=config, audio=audio)
            logging.info("Waiting for operation to complete...")
            response = operation.result(timeout=900)

        transcription = ""
        for result in response.results:
            words_info = result.alternatives[0].words
            for word_info in words_info:
                transcription += f"Speaker {word_info.speaker_tag}: {word_info.word} "

        logging.info("Transcription completed.")
        return transcription.strip()
    except Exception as e:
        logging.error(f"Error transcribing audio with diarization: {e}")
        return None



def save_transcription(transcription, output_file):
    try:
        with open(output_file, "w") as file:
            file.write(transcription)
        logging.info(f"Transcription saved to {output_file}")
    except Exception as e:
        logging.error(f"Error saving transcription: {e}")


def process_recording(recording_url):
    recording_sid = recording_url.split("/")[-1]
    downloaded_file = f"{recording_sid}.wav"
    converted_file = f"converted_{recording_sid}.wav"
    transcription_file = f"{recording_sid}_transcription.txt"

    if not download_recording(recording_url, downloaded_file):
        return

    file_to_transcribe = converted_file if is_valid_wav(downloaded_file) else convert_to_wav(downloaded_file, converted_file)
    if not file_to_transcribe:
        return

    transcription = transcribe_audio_with_diarization(file_to_transcribe)
    if transcription:
        save_transcription(transcription, transcription_file)

    try:
        os.remove(downloaded_file)
        os.remove(converted_file)
    except Exception as e:
        logging.error(f"Error cleaning up files: {e}")


def process_all_recordings():
    # Process recordings from the database
    recordings = get_unprocessed_recordings()
    for record in recordings:
        logging.info(f"Processing from database: {record.recording_url}")
        process_recording(record.recording_url)

    # Process recordings from the text file
    urls = read_recording_urls()
    for url in urls:
        logging.info(f"Processing from text file: {url}")
        process_recording(url)


if __name__ == "__main__":
    process_all_recordings()
