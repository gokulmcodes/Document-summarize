from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from bson import ObjectId
from gtts import gTTS
from deep_translator import GoogleTranslator
import pdfplumber
import docx
import re
import spacy
from werkzeug.utils import secure_filename
import os
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'secret_key'
app.config['MONGO_URI'] = "mongodb://localhost:27017/summary_app"
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
mongo = PyMongo(app)
CORS(app)

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.error("spaCy model 'en_core_web_sm' not found. Please run: python -m spacy download en_core_web_sm")
    raise

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# Check MongoDB connection
try:
    mongo.db.command("ping")
    logger.info("Connected to MongoDB successfully.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    print("Warning: MongoDB connection failed. Ensure MongoDB is running.")

# Serve audio files from UPLOAD_FOLDER
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    try:
        return render_template('register.html')
    except Exception as e:
        logger.error(f"Template error: {e}")
        return "Template not found. Please create register.html in the templates folder.", 500

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not all([name, email, username, password]):
            return jsonify({"status": "fail", "message": "All fields are required."})

        existing_user = mongo.db.users.find_one({"$or": [{"email": email}, {"username": username}]})
        if existing_user:
            return jsonify({"status": "fail", "message": "Email or username already exists."})

        hashed_pw = generate_password_hash(password)
        mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "username": username,
            "password": hashed_pw
        })

        return jsonify({"status": "success", "message": "Registration successful! Redirecting to login..."})
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"status": "fail", "message": "Registration failed."}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'GET':
            return render_template('login.html')
        data = request.get_json()
        identifier = data.get('identifier', '').strip()
        password = data.get('password', '').strip()

        user = mongo.db.users.find_one({
            "$or": [{"email": identifier}, {"username": identifier}]
        })

        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            return jsonify({"status": "success", "message": "Login successful! Redirecting to home..."})
        return jsonify({"status": "fail", "message": "Invalid email/username or password."})
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"status": "fail", "message": "Login failed."}), 500

@app.route('/home')
def home():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])}, {"password": 0})
        return render_template('home.html', user=user)
    except Exception as e:
        logger.error(f"Home route error: {e}")
        return "Error loading home page.", 500

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('index'))

        if request.method == 'POST':
            data = request.json
            mongo.db.users.update_one({"_id": ObjectId(user_id)}, {"$set": data})
            return jsonify({"status": "updated"})

        user = mongo.db.users.find_one({"_id": ObjectId(user_id)}, {"password": 0})
        return jsonify(user)
    except Exception as e:
        logger.error(f"Profile error: {e}")
        return jsonify({"status": "fail", "message": "Profile operation failed."}), 500

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        text = ""
        
        if 'file' in request.files:
            file = request.files['file']
            filename = secure_filename(file.filename)
            if not (file and filename.lower().endswith(('.pdf', '.doc', '.docx'))):
                return jsonify({'error': 'Only PDF, DOC, and DOCX files are supported.'})
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            if filename.lower().endswith('.pdf'):
                with pdfplumber.open(filepath) as pdf:
                    text = "".join(page.extract_text() or "" for page in pdf.pages)
            elif filename.lower().endswith(('.doc', '.docx')):
                doc = docx.Document(filepath)
                text = "\n".join(para.text.strip() for para in doc.paragraphs if para.text.strip())
        else:
            return jsonify({'error': 'No file uploaded'})

        if not text.strip():
            return jsonify({'error': 'No content to summarize'})

        # Use spaCy for summarization
        doc = nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents]
        if len(sentences) <= 2:
            summary = "<p>" + ". ".join(sentences) + ".</p>"
        else:
            # Simple extractive summarization: take top 2 sentences by length
            summary_sentences = sorted(sentences, key=len, reverse=True)[:2]
            summary = "<p>" + ". ".join(summary_sentences) + ".</p>"
        key_points = ["<ul>"] + [f"<li>{sent}</li>" for sent in summary_sentences] + ["</ul>"]
        return jsonify({'summary': summary + "".join(key_points), 'status': 'File uploaded successfully'})
    except Exception as e:
        logger.error(f"Summarize error: {e}")
        return jsonify({'error': f'Summarize failed: {str(e)}'}), 500

@app.route('/translate', methods=['POST'])
def translate():
    try:
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'en')

        translated = GoogleTranslator(source='auto', target=lang).translate(text)
        summary = f"<p>{translated}</p>"
        key_points = translated.split('. ')
        key_points_html = ["<ul>"] + [f"<li>{point}</li>" for point in key_points if point.strip()] + ["</ul>"]
        return jsonify({"translated": summary + "".join(key_points_html)})
    except Exception as e:
        logger.error(f"Translate error: {e}")
        return jsonify({'error': f'Translation failed: {str(e)}'}), 500

@app.route('/speak', methods=['POST'])
def speak():
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        lang = data.get('lang', 'en')

        if not text:
            return jsonify({'error': 'No text to speak'}), 400

        # Generate a unique filename to avoid overwrite conflicts
        audio_filename = f"speech_{uuid.uuid4().hex}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)

        tts = gTTS(text=text, lang=lang, tld='co.uk')
        tts.save(audio_path)
        logger.info(f"Audio file generated: {audio_path}")

        # Return the URL that the client can use to access the file
        return jsonify({'audio_path': f'/uploads/{audio_filename}'})
    except Exception as e:
        logger.error(f"Speak error: {e}")
        return jsonify({'error': f'Text-to-speech failed: {str(e)}'}), 500

@app.route('/logout')
def logout():
    try:
        session.pop('user_id', None)
        return redirect(url_for('login'))
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return "Error during logout.", 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)