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

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/studymate.git
   cd studymate
