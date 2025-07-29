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
from newspaper import Article  # For fetching content from URLs

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure random secret key
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
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    print("Warning: MongoDB connection failed. Ensure MongoDB is running.")

# Serve audio files from UPLOAD_FOLDER
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    try:
        if 'user_id' in session:
            return redirect(url_for('home'))
        return render_template('register.html')
    except Exception as e:
        logger.error(f"Template error on index route: {str(e)}")
        return jsonify({"status": "fail", "message": "Unable to load page."}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'GET':
            return render_template('register.html')
        
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
        logger.error(f"Registration error: {str(e)} with data: {data}")
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
        url = request.form.get('url', '').strip()  # Get URL from input
        file = request.files.get('file') if 'file' in request.files else None

        # Determine source and process content
        if url:
            try:
                article = Article(url)
                article.download()
                article.parse()
                text = article.text
            except Exception as e:
                return jsonify({'error': f'Failed to fetch URL content: {str(e)}'})
        elif file:
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
            return jsonify({'error': 'No URL or file provided'})

        if not text.strip():
            return jsonify({'error': 'No content to summarize'})

        # Enhanced summarization logic
        doc = nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]  # Filter short sentences
        if not sentences:
            return jsonify({'error': 'No valid sentences to summarize'})

        # Calculate sentence importance
        keyword_scores = {}
        for token in doc:
            if token.text.lower() not in nlp.Defaults.stop_words and token.is_alpha:
                keyword_scores[token.text.lower()] = keyword_scores.get(token.text.lower(), 0) + token.sentiment  # Use sentiment for weighting

        entity_weight = {}
        for ent in doc.ents:
            entity_weight[ent.text.lower()] = entity_weight.get(ent.text.lower(), 0) + 1  # Weight by entity frequency

        sentence_scores = {}
        for i, sent in enumerate(sentences):
            score = 0
            words = sent.lower().split()
            # Boost score for keywords and entities
            score += sum(keyword_scores.get(word, 0) for word in words if word in keyword_scores) * 0.6
            score += sum(entity_weight.get(word, 0) for word in words if word in entity_weight) * 0.4
            # Boost opening and closing sentences
            if i < len(sentences) * 0.1 or i > len(sentences) * 0.9:
                score += 0.2
            sentence_scores[i] = score / max(len(words), 1)  # Normalize by sentence length

        # Select top 4-5 sentences for a detailed summary
        num_sentences = min(max(4, len(sentences) // 10), 5)  # Dynamic based on content length
        top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:num_sentences]
        summary_sentences = [sentences[i] for i in sorted(top_indices)]

        # Construct summary with HTML formatting
        summary = "<p>" + ". ".join(summary_sentences) + ".</p>"
        key_points = ["<ul>"] + [f"<li>{sent.strip()}</li>" for sent in summary_sentences] + ["</ul>"]

        return jsonify({'summary': summary + "".join(key_points), 'status': 'Content processed successfully'})
    except Exception as e:
        logger.error(f"Summarize error: {str(e)} with url: {url}, file: {file}")
        return jsonify({'error': f'Summarize failed: {str(e)}'}), 500

@app.route('/translate', methods=['POST'])
def translate():
    try:
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'en')

        supported_langs = {
            'en': 'English',
            'hi': 'Hindi',
            'kn': 'Kannada',
            'ta': 'Tamil',
            'te': 'Telugu',
            'ur': 'Urdu'
        }
        if lang not in supported_langs:
            return jsonify({'error': 'Unsupported language'})

        translated = GoogleTranslator(source='auto', target=lang).translate(text)
        summary = f"<p>{translated}</p>"
        key_points = translated.split('. ')
        key_points_html = ["<ul>"] + [f"<li>{point}</li>" for point in key_points if point.strip()] + ["</ul>"]
        return jsonify({"translated": summary + "".join(key_points_html), "language": supported_langs[lang]})
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