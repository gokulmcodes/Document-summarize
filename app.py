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
from newspaper import Article

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MONGO_URI'] = "mongodb://localhost:27017/summary_app"
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
mongo = PyMongo(app)
CORS(app)

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.error("spaCy model 'en_core_web_sm' not found. Please run: python -m spacy download en_core_web_sm")
    raise

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

try:
    mongo.db.command("ping")
    logger.info("Connected to MongoDB successfully.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    print("Warning: MongoDB connection failed. Ensure MongoDB is running.")

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    try:
        return redirect(url_for('home' if 'user_id' in session else 'login'))
    except Exception as e:
        logger.error(f"Index route error: {str(e)}")
        return jsonify({"status": "fail", "message": "Unable to load page."}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'GET':
            return render_template('register.html')
        data = request.get_json()
        if not all([data.get(k, '').strip() for k in ['name', 'email', 'username', 'password']]):
            return jsonify({"status": "fail", "message": "All fields are required."})
        if mongo.db.users.find_one({"$or": [{"email": data['email']}, {"username": data['username']}]}):
            return jsonify({"status": "fail", "message": "Email or username already exists."})
        hashed_pw = generate_password_hash(data['password'])
        mongo.db.users.insert_one({k: data[k] for k in ['name', 'email', 'username']} | {"password": hashed_pw})
        return jsonify({"status": "success", "message": "Registration successful! Redirecting to login..."})
    except Exception as e:
        logger.error(f"Registration error: {str(e)} with data: {data}")
        return jsonify({"status": "fail", "message": "Registration failed."}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'GET':
            return render_template('login.html')
        data = request.get_json()
        identifier, password = data.get('identifier', '').strip(), data.get('password', '').strip()
        user = mongo.db.users.find_one({"$or": [{"email": identifier}, {"username": identifier}]})
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            return jsonify({"status": "success", "message": "Login successful! Redirecting to home..."})
        return jsonify({"status": "fail", "message": "Invalid email/username or password."})
    except Exception as e:
        logger.error(f"Login error: {str(e)} with data: {data}")
        return jsonify({"status": "fail", "message": "Login failed."}), 500

@app.route('/home')
def home():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])}, {"password": 0})
        return render_template('home.html', user=user)
    except Exception as e:
        logger.error(f"Home route error: {str(e)}")
        return jsonify({"status": "fail", "message": "Unable to load home page."}), 500

@app.route('/features')
def features():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('features.html')
    except Exception as e:
        logger.error(f"Features route error: {str(e)}")
        return jsonify({"status": "fail", "message": "Unable to load features page."}), 500

@app.route('/about')
def about():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('about.html')
    except Exception as e:
        logger.error(f"About route error: {str(e)}")
        return jsonify({"status": "fail", "message": "Unable to load about page."}), 500

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
        return render_template('profile.html', user=user)
    except Exception as e:
        logger.error(f"Profile error: {str(e)} with data: {data}")
        return jsonify({"status": "fail", "message": "Profile operation failed."}), 500

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        text = ""
        url = request.form.get('url', '').strip()
        files = request.files.getlist('files') if 'files' in request.files else []

        if url:
            try:
                article = Article(url)
                article.download()
                article.parse()
                text += article.text + "\n"
            except Exception as e:
                return jsonify({'error': f'Failed to fetch URL: {str(e)}'})

        if files:
            for file in files:
                filename = secure_filename(file.filename)
                if not filename.lower().endswith(('.pdf', '.doc', '.docx')):
                    return jsonify({'error': 'Only PDF, DOC, and DOCX files are supported.'})
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                if filename.lower().endswith('.pdf'):
                    with pdfplumber.open(filepath) as pdf:
                        text += "".join(page.extract_text() or "" for page in pdf.pages) + "\n"
                elif filename.lower().endswith(('.doc', '.docx')):
                    doc = docx.Document(filepath)
                    text += "\n".join(para.text.strip() for para in doc.paragraphs if para.text.strip()) + "\n"

        if not text.strip():
            return jsonify({'error': 'No content to summarize'})

        doc = nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]
        if not sentences:
            return jsonify({'error': 'No valid content to summarize'})

        # Enhanced summarization with flow
        keyword_weights = {token.text.lower(): token.sentiment + 0.1 for token in doc if token.is_alpha and token.pos_ in ['NOUN', 'VERB', 'ADJ'] and token.text.lower() not in nlp.Defaults.stop_words}
        entity_weights = {ent.text.lower(): len(ent.text.split()) * 0.5 for ent in doc.ents}
        sentence_scores = {}

        for i, sent in enumerate(sentences):
            words = sent.lower().split()
            score = sum(keyword_weights.get(word, 0) for word in words) * 0.6 + sum(entity_weights.get(word, 0) for word in words) * 0.3
            if i < len(sentences) * 0.1 or i > len(sentences) * 0.9:
                score += 0.2
            sentence_scores[i] = score / max(len(words), 1)

        num_sentences = min(max(3, int(len(sentences) * 0.25)), 5)
        top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:num_sentences]
        summary_sentences = [sentences[i] for i in sorted(top_indices)]

        # Create a flowing summary
        summary = " ".join(summary_sentences).replace('\n', ' ').strip()
        summary = re.sub(r'\s+', ' ', summary)  # Normalize spaces
        summary = f"The document highlights that {summary}. It provides key insights including {', '.join(summary_sentences[:2])}. Overall, the main focus is on {summary_sentences[-1].lower().replace('.', '')}."

        return jsonify({'summary': summary, 'status': 'Content processed successfully'})
    except Exception as e:
        logger.error(f"Summarize error: {str(e)} with url: {url}, files: {files}")
        return jsonify({'error': f'Summarize failed: {str(e)}'}), 500

@app.route('/translate', methods=['POST'])
def translate():
    try:
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'en')
        supported_langs = {'en': 'English', 'hi': 'Hindi', 'kn': 'Kannada', 'ta': 'Tamil', 'te': 'Telugu', 'ur': 'Urdu'}
        if lang not in supported_langs:
            return jsonify({'error': 'Unsupported language'})
        translated = GoogleTranslator(source='auto', target=lang).translate(text)
        return jsonify({"translated": translated, "language": supported_langs[lang]})
    except Exception as e:
        logger.error(f"Translate error: {str(e)} with data: {data}")
        return jsonify({'error': f'Translation failed: {str(e)}'}), 500

@app.route('/speak', methods=['POST'])
def speak():
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        lang = data.get('lang', 'en')
        if not text:
            return jsonify({'error': 'No text to speak'}), 400
        audio_filename = f"speech_{uuid.uuid4().hex}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        tts = gTTS(text=text, lang=lang, tld='co.uk')
        tts.save(audio_path)
        logger.info(f"Audio file generated: {audio_path}")
        return jsonify({'audio_path': f'/uploads/{audio_filename}'})
    except Exception as e:
        logger.error(f"Speak error: {str(e)} with data: {data}")
        return jsonify({'error': f'Text-to-speech failed: {str(e)}'}), 500

@app.route('/logout')
def logout():
    try:
        session.pop('user_id', None)
        return redirect(url_for('login'))
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({"status": "fail", "message": "Unable to logout."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)