This project is a full-stack voice recording and transcription system that leverages Twilio Voice API, OpenAI GPT-4, and Google Cloud Speech-to-Text to process, transcribe, and analyze recorded phone calls in real-time.

🎯 Key Features

📞 Twilio Voice API Integration – Handles incoming calls, captures voice input, and stores call metadata.
🗣️ GPT-4 Conversational AI – Provides intelligent, real-time voice interactions for a dynamic caller experience.
🎙️ Automated Speech Recognition (ASR) – Uses Google Cloud Speech-to-Text for high-accuracy transcription with speaker diarization.
🛠️ Flask Backend with SQLAlchemy – Stores caller responses, transcriptions, and call recordings in a structured relational database.
📂 Google Cloud Storage Support – Securely stores and processes audio files for long-term access and retrieval.
🔍 Data Logging & Debugging – Comprehensive logging for monitoring API interactions and database transactions.
📌 Tech Stack

Backend: Python, Flask, SQLAlchemy
APIs & Services: Twilio, OpenAI GPT-4, Google Cloud Speech-to-Text, Google Cloud Storage
Database: PostgreSQL / SQLite
Logging & Monitoring: Python Logging Module
📝 Usage

Deploy the Flask server and configure Twilio webhooks.
Initiate a call to the Twilio number and interact with the AI-powered system.
Transcriptions are processed, stored, and available for further analysis.
💡 Future Improvements

Enhanced NLP-based sentiment analysis.
Real-time voice authentication.
Multi-language transcription support.
