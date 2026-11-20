"""SQLAlchemy models for StudyMate accounts and study content."""

from __future__ import annotations

import datetime
import uuid

from extensions import db


class User(db.Model):
    """Represent an account and its owned study materials.

    Attributes:
        id: Database identifier.
        username: Unique account name.
        email: Unique account email.
        password: Hashed account password.
        flashcards: Cards owned by the account.
        flashcard_sets: Sets owned by the account.
        study_guides: Guides owned by the account.
    """

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    flashcards = db.relationship("Flashcard", backref="owner", lazy=True)
    flashcard_sets = db.relationship("FlashcardSet", backref="owner", lazy=True)
    study_guides = db.relationship("StudyGuide", backref="owner", lazy=True)


class Flashcard(db.Model):
    """Represent one question-and-answer card.

    Attributes:
        id: Database identifier.
        question: Prompt shown to the learner.
        answer: Response revealed to the learner.
        user_id: Owner's database identifier.
        flashcard_set_id: Optional containing set identifier.
    """

    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    # Link flashcards to a set (if applicable)
    flashcard_set_id = db.Column(db.String(36), db.ForeignKey("flashcard_set.id"))


class FlashcardSet(db.Model):
    """Group flashcards owned by one user.

    Attributes:
        id: Stable set identifier.
        name: User-visible set name.
        description: Optional set description.
        user_id: Owner's database identifier.
        flashcards: Cards assigned to this set.
    """

    __tablename__ = "flashcard_set"  # Explicit table name to match foreign key in Flashcard
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    # Relationship to access flashcards in this set
    flashcards = db.relationship("Flashcard", backref="flashcard_set", lazy=True)


class StudyGuide(db.Model):
    """Store generated guide text and its optional PDF representation.

    Attributes:
        id: Stable guide identifier.
        title: User-visible guide title.
        content: Guide text.
        user_id: Owner's database identifier.
        pdf_data: Optional generated PDF bytes.
    """

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pdf_data = db.Column(db.LargeBinary)
