"""Flask application routes and database models for StudyMate."""

from __future__ import annotations

import datetime
import io
import logging
import os
from functools import wraps
from typing import Any, Callable, TypeVar, cast

import jwt
from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from ai_services import generate_flashcards, generate_study_guide
from config import SECRET_KEY, create_secret_key
from document_processing import DocumentProcessingError, extract_document_text
from extensions import db
from models import Flashcard, FlashcardSet, StudyGuide, User
from pdf_utils import generate_pdf_from_content

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])

app = Flask(__name__)
app.config["SECRET_KEY"] = create_secret_key()
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///studymate.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

if not SECRET_KEY:
    logger.warning(
        "SECRET_KEY is unset; generated tokens are valid only until this process restarts."
    )

# ============================
#         Models
# ============================


def _user_from_token(token: str | None) -> User | None:
    """Resolve a valid authentication token to its account.

    Args:
        token: Signed JWT from the authentication cookie.

    Returns:
        The matching account, or ``None`` when the token is invalid or expired.
    """
    if not token:
        return None
    try:
        data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        user_id = data.get("user_id")
        return db.session.get(User, user_id) if user_id is not None else None
    except (
        AttributeError,
        jwt.InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
        SQLAlchemyError,
    ):
        logger.debug("Authentication token could not be resolved", exc_info=True)
        return None


# ============================
#    Authentication Utils
# ============================
def token_required(f: F) -> F:
    """Protect a route with the signed authentication cookie.

    Args:
        f: Flask view function to wrap.

    Returns:
        The wrapped view, which redirects unauthenticated requests to login.
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        """Authorize the request before calling the protected view."""
        token = request.cookies.get("token")

        if not token:
            return redirect(url_for("login"))  # Redirect to login if no token

        current_user = _user_from_token(token)
        if current_user is None:
            return redirect(url_for("login"))

        return f(current_user, *args, **kwargs)

    return cast(F, decorated)


# ============================
#         Routes
# ============================


@app.route("/")
def index() -> ResponseReturnValue:
    """Render the landing page or redirect an authenticated user.

    Returns:
        The landing page or a redirect response."""
    current_user = _user_from_token(request.cookies.get("token"))
    if current_user is not None:
        return redirect(url_for("dashboard"))

    return render_template("index.html")


# ----- Signup Endpoint (GET and POST) -----
@app.route("/signup", methods=["GET", "POST"])
def signup() -> ResponseReturnValue:
    """Render signup or create an account from submitted credentials.

    Returns:
        HTML for GET requests or a JSON result for POST requests."""
    if request.method == "GET":
        token = request.cookies.get("token")
        if token:
            if _user_from_token(token) is not None:
                return redirect(url_for("dashboard"))
        return render_template("signup.html")

    data = request.get_json()
    if not data or not all(k in data for k in ("username", "email", "password")):
        return jsonify({"message": "Missing fields"}), 400
    hashed_password = generate_password_hash(data["password"], method="pbkdf2:sha256")
    new_user = User(username=data["username"], email=data["email"], password=hashed_password)
    try:
        db.session.add(new_user)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Account creation failed")
        return jsonify(
            {"message": "User could not be created. Username or email might already exist."}
        ), 400
    return jsonify({"message": "User created successfully!"}), 201


# ----- Login Endpoint (GET and POST) -----
@app.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    """Render the login page or authenticate submitted credentials.

    Returns:
        HTML for GET requests or a token response for POST requests."""
    if request.method == "GET":
        token = request.cookies.get("token")
        if token:
            if _user_from_token(token) is not None:
                return redirect(url_for("dashboard"))
        return render_template("login.html")

    data = request.get_json()
    if not data or not all(k in data for k in ("login", "password")):
        return jsonify({"message": "Could not verify"}), 401

    user = User.query.filter(
        (User.username == data["login"]) | (User.email == data["login"])
    ).first()

    if not user or not check_password_hash(user.password, data["password"]):
        return jsonify({"message": "Invalid credentials"}), 401

    token = jwt.encode(
        {
            "user_id": user.id,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24),
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    response = jsonify({"token": token})
    response.set_cookie("token", token, httponly=True)
    return response


@app.route("/logout", methods=["GET"])
@token_required
def logout(current_user: User) -> ResponseReturnValue:
    """Clear the authentication cookie and return to the landing page.

    Args:
        current_user: Authenticated account being logged out.

    Returns:
        A redirect response with the token cookie removed."""
    response = make_response(redirect(url_for("index")))
    response.delete_cookie("token")
    return response


@app.route("/dashboard", methods=["GET"])
@token_required
def dashboard(current_user: User) -> ResponseReturnValue:
    """Render the dashboard for the authenticated account.

    Args:
        current_user: Account whose dashboard is requested.

    Returns:
        Rendered dashboard HTML."""
    return render_template("dashboard.html", user=current_user)


# ============================
#     Flashcard Endpoints
# ============================
@app.route("/flashcards", methods=["GET"])
@token_required
def get_flashcards(current_user: User) -> ResponseReturnValue:
    """Render the authenticated account’s flashcards and sets.

    Args:
        current_user: Account that owns the requested study materials.

    Returns:
        Rendered flashcards page."""
    flashcard_sets = FlashcardSet.query.filter_by(user_id=current_user.id).all()
    flashcards = Flashcard.query.filter_by(user_id=current_user.id).all()
    return render_template(
        "flashcards.html", flashcard_sets=flashcard_sets, flashcards=flashcards, user=current_user
    )


@app.route("/flashcards", methods=["POST"])
@token_required
def create_flashcard(current_user: User) -> ResponseReturnValue:
    """Creates a flashcard manually."""
    data = request.get_json()

    if not data or not all(k in data for k in ("question", "answer")):
        return jsonify({"message": "Missing question or answer"}), 400

    new_card = Flashcard(
        question=data["question"],
        answer=data["answer"],
        user_id=current_user.id,
    )
    db.session.add(new_card)
    db.session.commit()

    return jsonify({"message": "Flashcard created!", "flashcard_id": new_card.id}), 201


@app.route("/flashcards/ai", methods=["POST"])
@token_required
def create_ai_flashcards(current_user: User) -> ResponseReturnValue:
    """Generate flashcards from submitted text or an uploaded document.

    Args:
        current_user: Authenticated account that owns the request.

    Returns:
        A JSON response with flashcards or a validation/error message.
    """
    if "file" in request.files:
        uploaded_file = request.files["file"]
        if not uploaded_file.filename:
            return jsonify({"message": "No file selected"}), 400
        extension = os.path.splitext(uploaded_file.filename)[1].lower()
        try:
            content = extract_document_text(uploaded_file.read(), extension)
        except DocumentProcessingError as exc:
            return jsonify({"message": str(exc)}), 400
        data = request.form
    else:
        data = request.get_json(silent=True) or {}
        content = data.get("content")

    if not isinstance(content, str) or not content.strip():
        return jsonify({"message": "Content is required for AI-generated flashcards"}), 400

    raw_count = data.get("count")
    if isinstance(raw_count, bool):
        return jsonify({"message": "Flashcard count must be an integer"}), 400
    try:
        count = int(raw_count) if raw_count is not None else None
    except (TypeError, ValueError):
        return jsonify({"message": "Flashcard count must be an integer"}), 400

    try:
        flashcards = generate_flashcards(content, count)
    except (RuntimeError, ValueError) as exc:
        logger.warning("AI flashcard generation could not complete: %s", exc)
        return jsonify({"message": str(exc)}), 500
    except Exception:
        logger.exception("AI flashcard generation failed")
        return jsonify({"message": "AI flashcard generation failed"}), 500

    return jsonify(
        {
            "message": "AI-generated flashcards created!",
            "flashcards": flashcards,
            "count": len(flashcards),
        }
    ), 201


@app.route("/flashcards/<int:flashcard_id>", methods=["GET"])
@token_required
def get_flashcard(current_user: User, flashcard_id: int) -> ResponseReturnValue:
    """Return one flashcard owned by the authenticated account.

    Args:
        current_user: Account that owns the requested flashcard.
        flashcard_id: Database identifier of the flashcard.

    Returns:
        JSON response containing the flashcard or a not-found error."""
    card = Flashcard.query.filter_by(id=flashcard_id, user_id=current_user.id).first()
    if not card:
        return jsonify({"message": "Flashcard not found"}), 404
    card_data = {
        "id": card.id,
        "question": card.question,
        "answer": card.answer,
        "created_at": card.created_at,
    }
    return jsonify({"flashcard": card_data})


@app.route("/flashcards/<int:flashcard_id>", methods=["PUT"])
@token_required
def update_flashcard(current_user: User, flashcard_id: int) -> ResponseReturnValue:
    """Update a flashcard owned by the authenticated account.

    Args:
        current_user: Account that owns the requested flashcard.
        flashcard_id: Database identifier of the flashcard.

    Returns:
        JSON response describing the update result."""
    card = Flashcard.query.filter_by(id=flashcard_id, user_id=current_user.id).first()
    if not card:
        return jsonify({"message": "Flashcard not found"}), 404
    data = request.get_json()
    if "question" in data:
        card.question = data["question"]
    if "answer" in data:
        card.answer = data["answer"]
    db.session.commit()
    return jsonify({"message": "Flashcard updated!"})


@app.route("/flashcards/<int:flashcard_id>", methods=["DELETE"])
@token_required
def delete_flashcard(current_user: User, flashcard_id: int) -> ResponseReturnValue:
    """Delete a flashcard owned by the authenticated account.

    Args:
        current_user: Account that owns the requested flashcard.
        flashcard_id: Database identifier of the flashcard.

    Returns:
        JSON response describing the deletion result."""
    card = Flashcard.query.filter_by(id=flashcard_id, user_id=current_user.id).first()
    if not card:
        return jsonify({"message": "Flashcard not found"}), 404
    db.session.delete(card)
    db.session.commit()
    return jsonify({"message": "Flashcard deleted!"})


# ============================
#   Flashcard Set Endpoints
# ============================
@app.route("/flashcard-sets", methods=["GET"])
@token_required
def get_flashcard_sets(current_user: User) -> ResponseReturnValue:
    """List flashcard sets owned by the authenticated account.

    Args:
        current_user: Account whose sets are requested.

    Returns:
        JSON response containing the owned sets."""
    sets = FlashcardSet.query.filter_by(user_id=current_user.id).all()
    output = []
    for s in sets:
        set_data = {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "created_at": s.created_at,
        }
        output.append(set_data)
    return jsonify({"flashcard_sets": output})


@app.route("/flashcard-sets", methods=["POST"])
@token_required
def create_flashcard_set(current_user: User) -> ResponseReturnValue:
    """Create a flashcard set for the authenticated account.

    Args:
        current_user: Account that will own the new set.

    Returns:
        JSON response with the new set identifier or a validation error."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"message": "Missing name field"}), 400
    new_set = FlashcardSet(
        name=data["name"], description=data.get("description", ""), owner=current_user
    )
    db.session.add(new_set)
    db.session.commit()
    return jsonify({"message": "Flashcard set created!", "set_id": new_set.id}), 201


@app.route("/flashcard-sets/<string:set_id>/flashcards", methods=["GET"])
@token_required
def get_flashcards_in_set(current_user: User, set_id: str) -> ResponseReturnValue:
    """List cards in a set owned by the authenticated account.

    Args:
        current_user: Account that owns the requested set.
        set_id: Identifier of the flashcard set.

    Returns:
        JSON response containing the cards or a not-found error."""
    flashcard_set = FlashcardSet.query.filter_by(id=set_id, user_id=current_user.id).first()
    if not flashcard_set:
        return jsonify({"message": "Flashcard set not found"}), 404
    flashcards = Flashcard.query.filter_by(user_id=current_user.id, flashcard_set_id=set_id).all()
    return jsonify(
        {
            "flashcards": [
                {"id": f.id, "question": f.question, "answer": f.answer} for f in flashcards
            ]
        }
    )


@app.route("/flashcard-sets/<string:set_id>/flashcards", methods=["POST"])
@token_required
def create_flashcard_in_set(current_user: User, set_id: str) -> ResponseReturnValue:
    """Add a flashcard to an owned set.

    Args:
        current_user: Account that owns the set.
        set_id: Identifier of the flashcard set.

    Returns:
        JSON response with the created card or a validation error."""
    flashcard_set = FlashcardSet.query.filter_by(id=set_id, user_id=current_user.id).first()
    if not flashcard_set:
        return jsonify({"message": "Flashcard set not found"}), 404
    data = request.get_json()
    if not data or not all(k in data for k in ("question", "answer")):
        return jsonify({"message": "Missing question or answer"}), 400
    new_flashcard = Flashcard(
        question=data["question"],
        answer=data["answer"],
        user_id=current_user.id,
        flashcard_set_id=set_id,
    )
    db.session.add(new_flashcard)
    db.session.commit()
    return jsonify({"message": "Flashcard created!", "flashcard_id": new_flashcard.id}), 201


@app.route("/flashcard-sets/<string:set_id>", methods=["GET"])
@token_required
def get_flashcard_set(current_user: User, set_id: str) -> ResponseReturnValue:
    """Return one set owned by the authenticated account.

    Args:
        current_user: Account that owns the requested set.
        set_id: Identifier of the flashcard set.

    Returns:
        JSON response containing the set or a not-found error."""
    s = FlashcardSet.query.filter_by(id=set_id, user_id=current_user.id).first()
    if not s:
        return jsonify({"message": "Flashcard set not found"}), 404
    set_data = {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "created_at": s.created_at,
    }
    return jsonify({"flashcard_set": set_data})


@app.route("/flashcard-sets/<string:set_id>", methods=["PUT"])
@token_required
def update_flashcard_set(current_user: User, set_id: str) -> ResponseReturnValue:
    """Update metadata for an owned flashcard set.

    Args:
        current_user: Account that owns the set.
        set_id: Identifier of the flashcard set.

    Returns:
        JSON response describing the update result."""
    s = FlashcardSet.query.filter_by(id=set_id, user_id=current_user.id).first()
    if not s:
        return jsonify({"message": "Flashcard set not found"}), 404
    data = request.get_json()
    if "name" in data:
        s.name = data["name"]
    if "description" in data:
        s.description = data["description"]
    db.session.commit()
    return jsonify({"message": "Flashcard set updated!"})


@app.route("/flashcard-sets/<string:set_id>", methods=["DELETE"])
@token_required
def delete_flashcard_set(current_user: User, set_id: str) -> ResponseReturnValue:
    """Delete a set owned by the authenticated account.

    Args:
        current_user: Account that owns the set.
        set_id: Identifier of the flashcard set.

    Returns:
        JSON response describing the deletion result."""
    s = FlashcardSet.query.filter_by(id=set_id, user_id=current_user.id).first()
    if not s:
        return jsonify({"message": "Flashcard set not found"}), 404
    db.session.delete(s)
    db.session.commit()
    return jsonify({"message": "Flashcard set deleted!"})


# ============================
#    Study Guide Endpoints
# ============================
@app.route("/study-guides", methods=["GET"])
@token_required
def get_study_guides(current_user: User) -> ResponseReturnValue:
    """Render the study guides owned by the authenticated account.

    Args:
        current_user: Account whose study guides are requested.

    Returns:
        Rendered study guides page."""
    guides = StudyGuide.query.filter_by(user_id=current_user.id).all()
    study_guides = []
    for guide in guides:
        guide_data = {
            "id": guide.id,
            "name": guide.title,  # Changed from title to name to match template
            "content": guide.content,
        }
        study_guides.append(guide_data)
    return render_template("study_guides.html", study_guides=study_guides, user=current_user)


@app.route("/study-guides", methods=["POST"])
@token_required
def create_study_guide(current_user: User) -> ResponseReturnValue:
    """Create a study guide from submitted title and optional text.

    Args:
        current_user: Account that will own the new guide.

    Returns:
        JSON response with the new guide identifier or a validation error."""
    data = request.get_json()
    if not data or "title" not in data:
        return jsonify({"message": "Missing title field"}), 400
    # Use the provided manual input for content (if any)
    new_guide = StudyGuide(
        title=data["title"],
        content=data.get("content", ""),  # Updated to include manual input
        user_id=current_user.id,
    )
    db.session.add(new_guide)
    db.session.commit()
    return jsonify({"message": "Study guide created!", "guide_id": new_guide.id}), 201


@app.route("/study-guides/ai/<string:guide_id>", methods=["PUT"])
@token_required
def update_ai_study_guide(current_user: User, guide_id: str) -> ResponseReturnValue:
    """Regenerate a saved study guide from submitted text or a document.

    Args:
        current_user: Authenticated account that owns the guide.
        guide_id: Identifier of the guide to update.

    Returns:
        A JSON response with the updated guide or an error message.
    """
    guide = StudyGuide.query.filter_by(id=guide_id, user_id=current_user.id).first()
    if guide is None:
        return jsonify({"message": "Study guide not found or unauthorized"}), 404

    title = guide.title
    if "file" in request.files:
        uploaded_file = request.files["file"]
        if not uploaded_file.filename:
            return jsonify({"message": "No file selected"}), 400
        extension = os.path.splitext(uploaded_file.filename)[1].lower()
        try:
            content = extract_document_text(uploaded_file.read(), extension)
        except DocumentProcessingError as exc:
            return jsonify({"message": str(exc)}), 400
        title = request.form.get("title", title)
    elif request.is_json:
        data = request.get_json(silent=True) or {}
        content = data.get("content")
        title = data.get("title", title)
    else:
        content = request.form.get("content")
        title = request.form.get("title", title)

    if not isinstance(content, str) or not content.strip():
        return jsonify({"message": "Content is required for AI-generated study guide"}), 400

    try:
        generated_content = generate_study_guide(content)
        if not generated_content:
            return jsonify({"message": "The AI returned an empty study guide"}), 502
        pdf_data = generate_pdf_from_content(generated_content)
        guide.title = title
        guide.content = generated_content
        guide.pdf_data = pdf_data
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("AI study guide update failed")
        return jsonify({"message": "Failed to generate or save the study guide"}), 500

    return jsonify({"message": "Study guide updated!", "content": generated_content}), 200


@app.route("/study-guides/<string:guide_id>", methods=["GET"])
@token_required
def get_study_guide(current_user: User, guide_id: str) -> ResponseReturnValue:
    """Return one study guide owned by the authenticated account.

    Args:
        current_user: Account that owns the requested guide.
        guide_id: Identifier of the study guide.

    Returns:
        JSON response containing the guide or a not-found error."""
    guide = StudyGuide.query.filter_by(id=guide_id, user_id=current_user.id).first()
    if not guide:
        return jsonify({"message": "Study guide not found"}), 404

    # Check if PDF needs to be regenerated
    if not guide.pdf_data and guide.content:
        try:
            pdf_data = generate_pdf_from_content(guide.content)
            guide.pdf_data = pdf_data
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.warning("Could not regenerate study guide PDF", exc_info=True)

    guide_data = {
        "id": guide.id,
        "title": guide.title,
        "content": guide.content,
        "created_at": guide.created_at,
    }
    return jsonify({"study_guide": guide_data})


@app.route("/study-guides/<string:guide_id>", methods=["PUT"])
@token_required
def update_study_guide(current_user: User, guide_id: str) -> ResponseReturnValue:
    """Update the title, content, and PDF for an owned study guide.

    Args:
        current_user: Account that owns the requested guide.
        guide_id: Identifier of the study guide.

    Returns:
        JSON response describing the update result."""
    guide = StudyGuide.query.filter_by(id=guide_id, user_id=current_user.id).first()
    if not guide:
        return jsonify({"message": "Study guide not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"message": "Request body must be a JSON object"}), 400
    if "title" in data:
        guide.title = data["title"]
    if "content" in data:
        guide.content = data["content"]
        # Generate PDF data
        pdf_data = generate_pdf_from_content(data["content"])
        guide.pdf_data = pdf_data
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Study guide update failed")
        return jsonify({"message": "Study guide could not be updated"}), 500
    return jsonify({"message": "Study guide updated!"})


@app.route("/study-guides/<string:guide_id>", methods=["DELETE"])
@token_required
def delete_study_guide(current_user: User, guide_id: str) -> ResponseReturnValue:
    """Delete a study guide owned by the authenticated account.

    Args:
        current_user: Account that owns the requested guide.
        guide_id: Identifier of the study guide.

    Returns:
        JSON response describing the deletion result."""
    guide = StudyGuide.query.filter_by(id=guide_id, user_id=current_user.id).first()
    if not guide:
        return jsonify({"message": "Study guide not found"}), 404
    db.session.delete(guide)
    db.session.commit()
    return jsonify({"message": "Study guide deleted!"})


@app.route("/study-guides/<string:guide_id>/pdf", methods=["GET", "DELETE"])
@token_required
def handle_study_guide_pdf(current_user: User, guide_id: str) -> ResponseReturnValue:
    """Download or delete the PDF associated with a study guide.

    Args:
        current_user: Account that owns the requested guide.
        guide_id: Identifier of the study guide.

    Returns:
        PDF response or JSON describing the requested action."""
    guide = StudyGuide.query.filter_by(id=guide_id, user_id=current_user.id).first()
    if not guide:
        return jsonify({"message": "Study guide not found"}), 404

    if request.method == "DELETE":
        try:
            guide.content = ""
            guide.pdf_data = None
            pdf_path = os.path.join("static", "pdfs", f"{guide.id}.pdf")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)  # Remove the file on disk
            db.session.commit()
            return jsonify({"message": "PDF deleted!"}), 200
        except (OSError, SQLAlchemyError):
            db.session.rollback()
            logger.exception("Study guide PDF deletion failed")
            return jsonify({"message": "Failed to delete PDF"}), 500

    # GET method
    if not guide.pdf_data:
        try:
            pdf_data = generate_pdf_from_content(guide.content)
            guide.pdf_data = pdf_data
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Study guide PDF generation failed")
            return jsonify({"message": "Failed to generate PDF"}), 500

    return send_file(
        io.BytesIO(guide.pdf_data),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"study_guide_{guide.id}.pdf",
    )


# ============================
#         Main
# ============================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create tables if they don't exist. For production, use migrations.
    app.run(debug=False)
