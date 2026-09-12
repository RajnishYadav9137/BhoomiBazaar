import random
import time
from flask import Blueprint, render_template, request, redirect, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
import mysql.connector
from .db import get_db

auth = Blueprint("auth", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# =====================================================
# REGISTER (STEP 1: SEND OTP)
# =====================================================
@auth.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/dashboard")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not name or not mobile or not email or not password:
            flash("Please fill in all required fields.", "error")
            return render_template("register.html", name=name, mobile=mobile, email=email)

        if confirm_password and password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return render_template("register.html", name=name, mobile=mobile, email=email)

        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number.", "error")
            return render_template("register.html", name=name, mobile=mobile, email=email)

        db = None
        cursor = None

        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            # Check if email exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash("This email is already registered. Please login.", "error")
                return redirect("/login")

            # Check if mobile exists
            cursor.execute("SELECT id FROM users WHERE mobile = %s", (mobile,))
            if cursor.fetchone():
                flash("This mobile number is already registered. Please login or use a different number.", "error")
                return render_template("register.html", name=name, mobile=mobile, email=email)

            # Generate 6-digit OTP
            otp_code = str(random.randint(100000, 999999))

            # Store pending registration in session
            session["pending_reg"] = {
                "name": name,
                "mobile": mobile,
                "email": email,
                "password_hash": generate_password_hash(password),
                "otp": otp_code,
                "created_at": time.time()
            }

            flash(f"📱 OTP has been sent to +91 {mobile}. (Demo OTP Code: {otp_code})", "info")
            return redirect("/verify-otp")

        except mysql.connector.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return render_template("register.html", name=name, mobile=mobile, email=email)

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    return render_template("register.html")


# =====================================================
# VERIFY OTP (STEP 2: VERIFY & REGISTER)
# =====================================================
@auth.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "user_id" in session:
        return redirect("/dashboard")

    pending = session.get("pending_reg")
    if not pending:
        flash("No pending registration found. Please register first.", "error")
        return redirect("/register")

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        # Check OTP expiry (10 minutes)
        if time.time() - pending.get("created_at", 0) > 600:
            flash("OTP has expired. Please request a new OTP.", "error")
            return redirect("/resend-otp")

        if not entered_otp or entered_otp != pending.get("otp"):
            flash("Invalid OTP code. Please enter the correct 6-digit OTP.", "error")
            return render_template("verify_otp.html", mobile=pending["mobile"], demo_otp=pending["otp"])

        # OTP is correct -> Insert user into database
        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            sql = "INSERT INTO users (name, mobile, email, password) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (
                pending["name"],
                pending["mobile"],
                pending["email"],
                pending["password_hash"]
            ))
            db.commit()
            new_user_id = cursor.lastrowid

            # Clear pending registration and establish active session
            session.pop("pending_reg", None)
            session["user_id"] = new_user_id
            session["user_name"] = pending["name"]
            session["user_profile_pic"] = None

            flash(f"🎉 Welcome {pending['name']}! Your mobile number +91 {pending['mobile']} has been verified and your account is ready!", "success")
            return redirect("/dashboard")

        except mysql.connector.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return render_template("verify_otp.html", mobile=pending["mobile"], demo_otp=pending["otp"])

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    return render_template("verify_otp.html", mobile=pending["mobile"], demo_otp=pending["otp"])


# =====================================================
# RESEND OTP
# =====================================================
@auth.route("/resend-otp")
def resend_otp():
    pending = session.get("pending_reg")
    if not pending:
        flash("No pending registration found.", "error")
        return redirect("/register")

    new_otp = str(random.randint(100000, 999999))
    pending["otp"] = new_otp
    pending["created_at"] = time.time()
    session["pending_reg"] = pending

    flash(f"🔄 New OTP sent to +91 {pending['mobile']}. (Demo OTP Code: {new_otp})", "info")
    return redirect("/verify-otp")


# =====================================================
# LOGIN
# =====================================================
@auth.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect("/dashboard")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("login.html", email=email)

        db = None
        cursor = None

        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

        except mysql.connector.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return render_template("login.html", email=email)

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_profile_pic"] = user.get("profile_pic")
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect("/dashboard")
        else:
            flash("Invalid email or password. Please try again.", "error")
            return render_template("login.html", email=email)

    return render_template("login.html")


# =====================================================
# LOGOUT
# =====================================================
@auth.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect("/login")


# =====================================================
# PROFILE
# =====================================================
@auth.route("/profile")
def profile():
    if "user_id" not in session:
        flash("Please login to access your profile.", "error")
        return redirect("/login")

    db = None
    cursor = None
    user = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()

        if not user:
            session.clear()
            flash("User not found. Please login again.", "error")
            return redirect("/login")

        # Keep session profile pic updated
        session["user_profile_pic"] = user.get("profile_pic")

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect("/dashboard")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return render_template("profile.html", user=user)


# =====================================================
# EDIT PROFILE
# =====================================================
@auth.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        flash("Please login to edit your profile.", "error")
        return redirect("/login")

    db = None
    cursor = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        remove_pic = request.form.get("remove_pic", "0") == "1"
        new_pic = request.files.get("profile_pic")

        if not name or not mobile or not email:
            flash("Please fill in all required fields.", "error")
            return redirect("/edit-profile")

        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number.", "error")
            return redirect("/edit-profile")

        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            # Get current user record
            cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
            current_user = cursor.fetchone()

            if not current_user:
                session.clear()
                flash("User not found. Please login again.", "error")
                return redirect("/login")

            # Check if email is used by another user
            cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, session["user_id"]))
            if cursor.fetchone():
                flash("This email is already in use by another account.", "error")
                return redirect("/edit-profile")

            # Check if mobile is used by another user
            cursor.execute("SELECT id FROM users WHERE mobile = %s AND id != %s", (mobile, session["user_id"]))
            if cursor.fetchone():
                flash("This mobile number is already in use by another account.", "error")
                return redirect("/edit-profile")

            profile_pic_filename = current_user.get("profile_pic")

            # Handle new profile picture upload
            if new_pic and new_pic.filename != "":
                if not allowed_file(new_pic.filename):
                    flash("Only JPG, JPEG, PNG, WEBP, and GIF images are allowed for profile picture.", "error")
                    return redirect("/edit-profile")

                orig_filename = secure_filename(new_pic.filename)
                file_ext = os.path.splitext(orig_filename)[1]
                unique_filename = f"avatar_{uuid.uuid4().hex[:12]}{file_ext}"
                file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_filename)

                try:
                    new_pic.save(file_path)

                    # Delete old profile pic file if existed
                    if current_user.get("profile_pic"):
                        old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], current_user["profile_pic"])
                        if os.path.exists(old_path):
                            os.remove(old_path)

                    profile_pic_filename = unique_filename
                except Exception as e:
                    flash(f"Failed to save profile picture: {str(e)}", "error")
                    return redirect("/edit-profile")

            elif remove_pic:
                # User selected to remove their profile photo
                if current_user.get("profile_pic"):
                    old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], current_user["profile_pic"])
                    if os.path.exists(old_path):
                        os.remove(old_path)
                profile_pic_filename = None

            cursor.execute(
                "UPDATE users SET name = %s, mobile = %s, email = %s, profile_pic = %s WHERE id = %s",
                (name, mobile, email, profile_pic_filename, session["user_id"])
            )
            db.commit()

            session["user_name"] = name
            session["user_profile_pic"] = profile_pic_filename
            flash("Profile updated successfully!", "success")
            return redirect("/profile")

        except mysql.connector.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return redirect("/edit-profile")

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect("/profile")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return render_template("edit_profile.html", user=user)


# =====================================================
# CHANGE PASSWORD
# =====================================================
@auth.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        flash("Please login to change your password.", "error")
        return redirect("/login")

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_password or not new_password or not confirm_password:
            flash("Please fill in all password fields.", "error")
            return render_template("change_password.html")

        if new_password != confirm_password:
            flash("New password and confirm password do not match.", "error")
            return render_template("change_password.html")

        if len(new_password) < 6:
            flash("New password must be at least 6 characters long.", "error")
            return render_template("change_password.html")

        db = None
        cursor = None

        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            cursor.execute("SELECT password FROM users WHERE id = %s", (session["user_id"],))
            user = cursor.fetchone()

            if not user or not check_password_hash(user["password"], current_password):
                flash("Current password is incorrect.", "error")
                return render_template("change_password.html")

            hashed_new_password = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_new_password, session["user_id"]))
            db.commit()

            session.clear()
            flash("Password changed successfully! Please login with your new password.", "success")
            return redirect("/login")

        except mysql.connector.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return render_template("change_password.html")

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    return render_template("change_password.html")
