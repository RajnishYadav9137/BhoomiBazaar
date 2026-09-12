from flask import Blueprint, render_template, request, redirect, session, flash, current_app, jsonify
from werkzeug.utils import secure_filename
import os
import uuid
import base64
import mysql.connector
from .db import get_db

views = Blueprint("views", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_base64_image(base64_data, upload_folder):
    """Saves a base64 data URL to an image file and returns the generated filename."""
    if not base64_data or not base64_data.startswith("data:image/"):
        return None
    try:
        header, encoded = base64_data.split(",", 1)
        mime_part = header.split(";")[0]
        ext_part = mime_part.split("/")[-1].lower()
        if ext_part == "jpeg":
            ext = ".jpg"
        elif ext_part in ["png", "webp", "jpg", "gif"]:
            ext = f".{ext_part}"
        else:
            ext = ".jpg"
        
        file_bytes = base64.b64decode(encoded)
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(upload_folder, unique_filename)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        return unique_filename
    except Exception:
        return None


# =====================================================
# PUBLIC STATIC PAGES
# =====================================================
@views.route("/")
def home():
    return render_template("index.html")


@views.route("/about")
def about():
    return render_template("about.html")


@views.route("/services")
def services():
    return render_template("services.html")


@views.route("/contact")
def contact():
    return render_template("contact.html")


# =====================================================
# DASHBOARD
# =====================================================
@views.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please login to access the dashboard.", "error")
        return redirect("/login")

    db = None
    cursor = None
    user = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, mobile, profile_pic FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()
    except mysql.connector.Error:
        pass
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    user_name = user["name"] if user else session.get("user_name", "User")
    profile_pic = user.get("profile_pic") if user else session.get("user_profile_pic")

    return render_template("dashboard.html", name=user_name, profile_pic=profile_pic)


# =====================================================
# SELL LAND (ADD LISTING)
# =====================================================
@views.route("/sell-land", methods=["GET", "POST"])
def sell_land():
    if "user_id" not in session:
        flash("Please login to list your land for sale.", "error")
        return redirect("/login")

    if request.method == "GET":
        return render_template("sell_land.html")

    title = request.form.get("title", "").strip()
    location = request.form.get("location", "").strip()
    area = request.form.get("area", "").strip()
    price = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    latitude_text = request.form.get("latitude", "").strip()
    longitude_text = request.form.get("longitude", "").strip()
    image = request.files.get("image")

    status = request.form.get("status", "Available").strip()
    if status not in ["Available", "Sold"]:
        status = "Available"

    # Validation
    if not title or not location or not area or not price or not description:
        flash("Please fill in all required fields.", "error")
        return render_template("sell_land.html")

    # Latitude validation
    latitude = None
    if latitude_text:
        try:
            latitude = float(latitude_text)
            if not (-90 <= latitude <= 90):
                flash("Latitude must be between -90 and 90.", "error")
                return render_template("sell_land.html")
        except ValueError:
            flash("Invalid Latitude format.", "error")
            return render_template("sell_land.html")

    # Longitude validation
    longitude = None
    if longitude_text:
        try:
            longitude = float(longitude_text)
            if not (-180 <= longitude <= 180):
                flash("Longitude must be between -180 and 180.", "error")
                return render_template("sell_land.html")
        except ValueError:
            flash("Invalid Longitude format.", "error")
            return render_template("sell_land.html")

    # Image upload / Live camera capture
    image = request.files.get("image")
    captured_data = request.form.get("captured_image_data", "").strip()

    unique_filename = None
    file_path = None

    if image and image.filename != "":
        if not allowed_file(image.filename):
            flash("Only JPG, JPEG, PNG, WEBP, and GIF images are allowed.", "error")
            return render_template("sell_land.html")

        original_filename = secure_filename(image.filename)
        file_ext = os.path.splitext(original_filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            image.save(file_path)
        except Exception as e:
            flash(f"Failed to save uploaded photo: {str(e)}", "error")
            return render_template("sell_land.html")

    elif captured_data and captured_data.startswith("data:image/"):
        unique_filename = save_base64_image(captured_data, current_app.config["UPLOAD_FOLDER"])
        if not unique_filename:
            flash("Failed to process live captured photo. Please try again or upload a photo file.", "error")
            return render_template("sell_land.html")
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_filename)

    else:
        flash("Please upload a photo or take a live camera shot of the land.", "error")
        return render_template("sell_land.html")

    # Save to Database
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()

        sql = """
            INSERT INTO lands 
            (seller_id, title, location, area, price, description, image, latitude, longitude, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (
            session["user_id"],
            title,
            location,
            area,
            price,
            description,
            unique_filename,
            latitude,
            longitude,
            status
        ))
        db.commit()

        flash("🏡 Land listing published successfully!", "success")
        return redirect("/my-lands")

    except mysql.connector.Error as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        flash(f"Database error: {str(e)}", "error")
        return render_template("sell_land.html")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =====================================================
# EDIT LAND
# =====================================================
@views.route("/edit-land/<int:land_id>", methods=["GET", "POST"])
def edit_land(land_id):
    if "user_id" not in session:
        flash("Please login to edit your listing.", "error")
        return redirect("/login")

    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM lands WHERE id = %s", (land_id,))
        land = cursor.fetchone()

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect("/my-lands")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    if not land:
        flash("Land listing not found.", "error")
        return redirect("/my-lands")

    # Security check: User must be the seller
    if land["seller_id"] != session["user_id"]:
        flash("You are not authorized to edit this land listing.", "error")
        return redirect("/my-lands")

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        location = request.form.get("location", "").strip()
        area = request.form.get("area", "").strip()
        price = request.form.get("price", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "Available").strip()
        latitude_text = request.form.get("latitude", "").strip()
        longitude_text = request.form.get("longitude", "").strip()
        new_image = request.files.get("image")

        if not title or not location or not area or not price or not description:
            flash("Please fill in all required fields.", "error")
            return render_template("edit_land.html", land=land)

        if status not in ["Available", "Sold"]:
            status = "Available"

        # Latitude validation
        latitude = None
        if latitude_text:
            try:
                latitude = float(latitude_text)
                if not (-90 <= latitude <= 90):
                    flash("Latitude must be between -90 and 90.", "error")
                    return render_template("edit_land.html", land=land)
            except ValueError:
                flash("Invalid Latitude format.", "error")
                return render_template("edit_land.html", land=land)

        # Longitude validation
        longitude = None
        if longitude_text:
            try:
                longitude = float(longitude_text)
                if not (-180 <= longitude <= 180):
                    flash("Longitude must be between -180 and 180.", "error")
                    return render_template("edit_land.html", land=land)
            except ValueError:
                flash("Invalid Longitude format.", "error")
                return render_template("edit_land.html", land=land)

        image_filename = land["image"]
        captured_data = request.form.get("captured_image_data", "").strip()

        # Handle optional new image upload or live camera capture
        if new_image and new_image.filename != "":
            if not allowed_file(new_image.filename):
                flash("Only JPG, JPEG, PNG, WEBP, and GIF images are allowed.", "error")
                return render_template("edit_land.html", land=land)

            orig_filename = secure_filename(new_image.filename)
            file_ext = os.path.splitext(orig_filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            new_file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_filename)

            try:
                new_image.save(new_file_path)
                # Remove old image file
                if land["image"]:
                    old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], land["image"])
                    if os.path.exists(old_path):
                        os.remove(old_path)
                image_filename = unique_filename
            except Exception as e:
                flash(f"Failed to upload new photo: {str(e)}", "error")
                return render_template("edit_land.html", land=land)

        elif captured_data and captured_data.startswith("data:image/"):
            unique_filename = save_base64_image(captured_data, current_app.config["UPLOAD_FOLDER"])
            if unique_filename:
                # Remove old image file
                if land["image"]:
                    old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], land["image"])
                    if os.path.exists(old_path):
                        os.remove(old_path)
                image_filename = unique_filename
            else:
                flash("Failed to process live captured photo. Please try again.", "error")
                return render_template("edit_land.html", land=land)

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()

            sql = """
                UPDATE lands
                SET title = %s, location = %s, area = %s, price = %s,
                    description = %s, latitude = %s, longitude = %s,
                    status = %s, image = %s
                WHERE id = %s AND seller_id = %s
            """
            cursor.execute(sql, (
                title,
                location,
                area,
                price,
                description,
                latitude,
                longitude,
                status,
                image_filename,
                land_id,
                session["user_id"]
            ))
            db.commit()

            flash("🏡 Land details updated successfully!", "success")
            return redirect("/my-lands")

        except mysql.connector.Error as e:
            flash(f"Database error: {str(e)}", "error")
            return render_template("edit_land.html", land=land)

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    return render_template("edit_land.html", land=land)


# =====================================================
# DELETE LAND
# =====================================================
@views.route("/delete-land/<int:land_id>", methods=["POST"])
def delete_land(land_id):
    if "user_id" not in session:
        flash("Please login to perform this action.", "error")
        return redirect("/login")

    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM lands WHERE id = %s", (land_id,))
        land = cursor.fetchone()

        if not land:
            flash("Land listing not found.", "error")
            return redirect("/my-lands")

        # Security check: User must be the owner
        if land["seller_id"] != session["user_id"]:
            flash("You are not authorized to delete this land listing.", "error")
            return redirect("/my-lands")

        # Delete image file
        if land["image"]:
            img_path = os.path.join(current_app.config["UPLOAD_FOLDER"], land["image"])
            if os.path.exists(img_path):
                os.remove(img_path)

        # Delete from database
        cursor.execute("DELETE FROM lands WHERE id = %s AND seller_id = %s", (land_id, session["user_id"]))
        db.commit()

        flash("🗑️ Land listing deleted successfully!", "success")

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return redirect("/my-lands")


# =====================================================
# TOGGLE LAND STATUS (Available / Sold)
# =====================================================
@views.route("/toggle-status/<int:land_id>", methods=["POST"])
def toggle_status(land_id):
    if "user_id" not in session:
        flash("Please login to perform this action.", "error")
        return redirect("/login")

    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT id, seller_id, status FROM lands WHERE id = %s", (land_id,))
        land = cursor.fetchone()

        if not land:
            flash("Land listing not found.", "error")
            return redirect("/my-lands")

        if land["seller_id"] != session["user_id"]:
            flash("You are not authorized to update this listing.", "error")
            return redirect("/my-lands")

        new_status = "Sold" if land["status"] == "Available" else "Available"

        cursor.execute(
            "UPDATE lands SET status = %s WHERE id = %s AND seller_id = %s",
            (new_status, land_id, session["user_id"])
        )
        db.commit()

        status_msg = f"Status updated to '{new_status}' successfully!"
        flash(f"🔄 {status_msg}", "success")

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return redirect("/my-lands")


# =====================================================
# MY LANDS
# =====================================================
@views.route("/my-lands")
def my_lands():
    if "user_id" not in session:
        flash("Please login to view your listings.", "error")
        return redirect("/login")

    db = None
    cursor = None
    lands = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        sql = "SELECT * FROM lands WHERE seller_id = %s ORDER BY id DESC"
        cursor.execute(sql, (session["user_id"],))
        lands = cursor.fetchall()

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return render_template("my_lands.html", lands=lands)


# =====================================================
# ALL AVAILABLE LANDS
# =====================================================
@views.route("/lands")
def lands():
    db = None
    cursor = None
    all_lands = []
    status_filter = request.args.get("status", "All").strip()
    user_wishlist_ids = set()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if status_filter in ["Available", "Sold"]:
            sql = """
                SELECT lands.*, 
                       users.name AS seller_name, 
                       users.email AS seller_email, 
                       users.mobile AS seller_mobile,
                       users.profile_pic AS seller_profile_pic
                FROM lands
                JOIN users ON lands.seller_id = users.id
                WHERE lands.status = %s
                ORDER BY lands.id DESC
            """
            cursor.execute(sql, (status_filter,))
        else:
            status_filter = "All"
            sql = """
                SELECT lands.*, 
                       users.name AS seller_name, 
                       users.email AS seller_email, 
                       users.mobile AS seller_mobile,
                       users.profile_pic AS seller_profile_pic
                FROM lands
                JOIN users ON lands.seller_id = users.id
                ORDER BY lands.id DESC
            """
            cursor.execute(sql)

        all_lands = cursor.fetchall()

        # Fetch wishlist IDs if user is logged in
        if "user_id" in session:
            cursor.execute("SELECT land_id FROM wishlist WHERE user_id = %s", (session["user_id"],))
            user_wishlist_ids = {row["land_id"] for row in cursor.fetchall()}

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return render_template("lands.html", lands=all_lands, current_filter=status_filter, user_wishlist_ids=user_wishlist_ids)


# =====================================================
# LAND DETAILS
# =====================================================
@views.route("/land/<int:land_id>")
def land_details(land_id):
    db = None
    cursor = None
    land = None
    is_wishlisted = False

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        sql = """
            SELECT 
                lands.*, 
                users.name AS seller_name, 
                users.email AS seller_email, 
                users.mobile AS seller_mobile,
                users.profile_pic AS seller_profile_pic
            FROM lands
            JOIN users ON lands.seller_id = users.id
            WHERE lands.id = %s
        """
        cursor.execute(sql, (land_id,))
        land = cursor.fetchone()

        if land and "user_id" in session:
            cursor.execute(
                "SELECT id FROM wishlist WHERE user_id = %s AND land_id = %s",
                (session["user_id"], land_id)
            )
            is_wishlisted = bool(cursor.fetchone())

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect("/lands")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    if not land:
        flash("Land listing not found.", "error")
        return redirect("/lands")

    return render_template("land_details.html", land=land, is_wishlisted=is_wishlisted)


# =====================================================
# TOGGLE WISHLIST (SAVE / UNSAVE PROPERTY)
# =====================================================
@views.route("/toggle-wishlist/<int:land_id>", methods=["GET", "POST"])
def toggle_wishlist(land_id):
    if "user_id" not in session:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": False, "error": "login_required", "message": "Please login to save to your wishlist."}), 401
        flash("Please login to save lands to your Wishlist.", "error")
        return redirect("/login")

    db = None
    cursor = None
    action = "added"
    is_saved = True

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Check if already in wishlist
        cursor.execute(
            "SELECT id FROM wishlist WHERE user_id = %s AND land_id = %s",
            (session["user_id"], land_id)
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "DELETE FROM wishlist WHERE user_id = %s AND land_id = %s",
                (session["user_id"], land_id)
            )
            db.commit()
            action = "removed"
            is_saved = False
            flash("Removed from your Wishlist.", "info")
        else:
            cursor.execute(
                "INSERT INTO wishlist (user_id, land_id) VALUES (%s, %s)",
                (session["user_id"], land_id)
            )
            db.commit()
            action = "added"
            is_saved = True
            flash("❤️ Land saved to your Wishlist!", "success")

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({
                "success": True,
                "action": action,
                "is_saved": is_saved,
                "land_id": land_id,
                "message": "Saved to Wishlist" if is_saved else "Removed from Wishlist"
            })

    except mysql.connector.Error as e:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": False, "error": str(e)}), 500
        flash(f"Database error: {str(e)}", "error")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    # Redirect back to where the request came from
    referrer = request.referrer
    if referrer and "/login" not in referrer:
        return redirect(referrer)
    return redirect("/lands")


# =====================================================
# USER WISHLIST (MY SAVED LANDS)
# =====================================================
@views.route("/wishlist")
def wishlist():
    if "user_id" not in session:
        flash("Please login to view your Wishlist / Saved Lands.", "error")
        return redirect("/login")

    db = None
    cursor = None
    saved_lands = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        sql = """
            SELECT lands.*, 
                   users.name AS seller_name, 
                   users.email AS seller_email, 
                   users.mobile AS seller_mobile,
                   users.profile_pic AS seller_profile_pic,
                   wishlist.created_at AS saved_at
            FROM wishlist
            JOIN lands ON wishlist.land_id = lands.id
            JOIN users ON lands.seller_id = users.id
            WHERE wishlist.user_id = %s
            ORDER BY wishlist.id DESC
        """
        cursor.execute(sql, (session["user_id"],))
        saved_lands = cursor.fetchall()

    except mysql.connector.Error as e:
        flash(f"Database error: {str(e)}", "error")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return render_template("wishlist.html", lands=saved_lands)

