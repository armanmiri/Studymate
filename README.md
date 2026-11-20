# 📚 StudyMate: The Four Musketeers

**StudyMate** is an AI-powered study assistant developed as part of the CSEN 174 project "The Four Musketeers." This Flask-based web application helps students study more effectively by allowing them to generate, manage, and interact with study materials — including flashcards and summaries — using modern AI and document processing tools.

---

## 🚀 Features

- 🔐 **User Authentication**
  - Secure login and registration using JWT.
  - Passwords stored with strong hashing via `werkzeug.security`.

- 📄 **Document Parsing**
  - Upload and process files in multiple formats:
    - PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx)
    - Images (OCR supported via `pytesseract`)
    - Plain text and other supported formats via `textract`

- 🤖 **AI Integration**
  - Uses Google's Gemini API to:
    - Generate flashcards
    - Summarize documents
    - Provide AI-powered study assistance

- 🧠 **Flashcards & Study Tools**
  - Create, view, and interact with flashcards.
  - Potential for personalized quiz and spaced repetition features.

- 🧾 **PDF Report Generation**
  - Automatically generate and download study summaries or notes in PDF format using `reportlab`.

- 🗂️ **SQLite Database**
  - All user data and content is securely stored using SQLAlchemy ORM with a local SQLite database.

---

## 🛠 Tech Stack

- **Backend**: Flask, SQLAlchemy, JWT, Google Gemini API
- **Frontend**: HTML, CSS, JavaScript (via Flask templates)
- **Database**: SQLite
- **File Handling**: `PyPDF2`, `python-docx`, `python-pptx`, `pandas`, `pytesseract`, `textract`

---

## 📦 Installation

Use Python 3.11 or newer. Install runtime dependencies with
`python -m pip install -r requirements.txt`. Set `GEMINI_API_KEY` to enable
AI generation and set a persistent random `SECRET_KEY` to keep login tokens
valid after restarts. The app uses a temporary process-local key when
`SECRET_KEY` is unset and logs a warning.

For development, install `requirements-dev.txt` and run `python -m ruff check .`
and `python -m ruff format --check .`. Follow PEP 8, use four spaces, keep
lines at or below 100 characters, annotate public signatures, and document
public classes and functions with Google-style docstrings. Apply length and
complexity thresholds to new and changed code as existing files are edited.

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/studymate.git
   cd studymate
