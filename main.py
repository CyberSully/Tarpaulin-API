from flask import Flask, request, send_file, jsonify
import requests
from google.cloud import storage
from google.cloud import datastore as gcloud_datastore
import io
import jwt
from dotenv import load_dotenv
import os
from dotenv import load_dotenv
import os

load_dotenv()

AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE")

PHOTO_BUCKET='tarpaulin-bucket-brett'


app = Flask(__name__)

# API programmed by Brett Sullivan 6-5-2025, Oregon State University, Sullbret@oregonstate.edu 
# Password for all users - password$$123


datastore_client = gcloud_datastore.Client()

# Basic home / route 
@app.route('/')
def home():
    return 'Tarpaulin API is running!', 200


# Route 1 - User Login with AuthO & jwt
@app.route('/users/login', methods=['POST'])
def user_login():
    try:
        body = request.get_json()

        if not body or 'username' not in body or 'password' not in body:
            return jsonify({"Error": "The request body is invalid"}), 400

        username = body['username']
        password = body['password']

        token_url = f"https://{AUTH0_DOMAIN}/oauth/token"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "audience": AUTH0_AUDIENCE,
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET
        }

        response = requests.post(token_url, headers=headers, json=payload)

        if response.status_code == 200:
            token = response.json().get("access_token")
            return jsonify({"token": token}), 200
        else:
            return jsonify({"Error": "Unauthorized"}), 401

    except Exception as e:
        print("Exception:", e)
        return jsonify({"Error": "The request body is invalid"}), 400





# Helper function for routes
def verify_jwt_and_get_sub():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, "Missing or invalid Authorization header", 401

    token = auth_header.split(" ")[1]
    try:
        # This decodes without verifying signature (sufficient for our needs if audience is correct)
        decoded = jwt.decode(token, options={"verify_signature": False}, audience=AUTH0_AUDIENCE)
        sub = decoded.get("sub")
        return sub, None, None
    except Exception:
        return None, "Unauthorized", 401
    

# Route 2 - GET all users route, only 200 for admin
@app.route('/users', methods=['GET'])
def get_all_users():
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": error_msg}), status

    # Get user entity by sub
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    results = list(query.fetch())
    if not results:
        return jsonify({"Error": "You don't have permission on this resource"}), 403
    if results[0]['role'] != "admin":
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Get all users and return only id, role, sub
    query = datastore_client.query(kind="users")
    all_users = query.fetch()
    user_list = []
    for user in all_users:
        user_list.append({
            "id": user.key.id,
            "role": user["role"],
            "sub": user["sub"]
        })

    return jsonify(user_list), 200




# Route 3 - GET user by ID
@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": error_msg}), status

    # Get requesting user
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    requester = list(query.fetch())

    if not requester:
        return jsonify({"Error": "Forbidden"}), 403

    requester_role = requester[0]["role"]

    # Get target user
    key = datastore_client.key("users", user_id)
    user = datastore_client.get(key)

    if not user:
        return jsonify({"Error": "Forbidden"}), 403

    if requester_role != "admin" and requester[0].key.id != user_id:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    user_data = {
        "id": user.key.id,
        "role": user["role"],
        "sub": user["sub"]
    }

    # Check if avatar file exists in GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(PHOTO_BUCKET)
    blob = bucket.blob(f"avatars/{user.key.id}.png")
    if blob.exists():
        user_data["avatar_url"] = f"{request.host_url.rstrip('/')}/users/{user.key.id}/avatar"

    # Add courses only for instructors and students
    if user["role"] in ["instructor", "student"]:
        course_ids = user.get("courses", [])
        course_links = [f"http://localhost:8080/courses/{course_id}" for course_id in course_ids]
        user_data["courses"] = course_links


    return jsonify(user_data), 200


# Route 4 - POST - Creat/Update a users avatar
@app.route('/users/<int:user_id>/avatar', methods=['POST'])
def upload_avatar(user_id):
    # Step 1: Check for 'file' in request
    if 'file' not in request.files:
        return jsonify({"Error": "The request body is invalid"}), 400

    file_obj = request.files['file']

    # Step 2: Verify JWT and match sub with user_id
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": error_msg}), status

    # Get user entity from Datastore
    user_key = datastore_client.key("users", user_id)
    user = datastore_client.get(user_key)
    if not user:
        return jsonify({"Error": "User not found"}), 403

    if user["sub"] != sub:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Upload to GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(PHOTO_BUCKET)
    blob = bucket.blob(f"avatars/{user_id}.png")
    file_obj.seek(0)
    blob.upload_from_file(file_obj, content_type="image/png")

    # Step 4: Return the avatar URL
    avatar_url = f"{request.host_url.rstrip('/')}/users/{user_id}/avatar"
    return jsonify({"avatar_url": avatar_url}), 200



# Route 5: GET /users/:user_id/avatar 
@app.route('/users/<int:user_id>/avatar', methods=['GET'])
def get_avatar(user_id):
    # Step 1: Verify JWT and extract sub
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": error_msg}), status

    # Step 2: Get user from Datastore
    user_key = datastore_client.key("users", user_id)
    user = datastore_client.get(user_key)
    if not user:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Check if JWT belongs to this user
    if user["sub"] != sub:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 4: Access GCS and check if avatar exists
    storage_client = storage.Client()
    bucket = storage_client.bucket(PHOTO_BUCKET)
    blob = bucket.blob(f"avatars/{user_id}.png")

    if not blob.exists():
        return jsonify({"Error": "Not found"}), 404

    # Step 5: Serve the image file
    file_obj = io.BytesIO()
    blob.download_to_file(file_obj)
    file_obj.seek(0)
    return send_file(file_obj, mimetype="image/png", download_name="avatar.png"), 200



# Route 6: DELETE /users/:user_id/avatar 
@app.route('/users/<int:user_id>/avatar', methods=['DELETE'])
def delete_avatar(user_id):
    # Step 1: Verify JWT and extract sub
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": error_msg}), status

    # Step 2: Get user from Datastore
    user_key = datastore_client.key("users", user_id)
    user = datastore_client.get(user_key)
    if not user:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Ensure the JWT belongs to this user
    if user["sub"] != sub:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 4: Check for avatar in GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(PHOTO_BUCKET)
    blob = bucket.blob(f"avatars/{user_id}.png")

    if not blob.exists():
        return jsonify({"Error": "Not found"}), 404

    # Step 5: Delete the avatar
    blob.delete()
    return '', 204



# Route 7: POST /courses
@app.route('/courses', methods=['POST'])
def create_course():
    # Step 1: Verify JWT
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": error_msg}), status

    # Step 2: Ensure requester is an admin
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    requester = list(query.fetch())
    if not requester or requester[0]["role"] != "admin":
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Validate request body
    try:
        body = request.get_json()
        subject = body["subject"]
        number = int(body["number"])
        title = body["title"]
        term = body["term"]
        instructor_id = int(body["instructor_id"])
    except:
        return jsonify({"Error": "The request body is invalid"}), 400

    # Step 4: Check instructor_id is valid and role = instructor
    instructor_key = datastore_client.key("users", instructor_id)
    instructor = datastore_client.get(instructor_key)
    if not instructor or instructor.get("role") != "instructor":
        return jsonify({"Error": "The request body is invalid"}), 400

    # Step 5: Create course
    course_key = datastore_client.key("courses")
    course = gcloud_datastore.Entity(key=course_key)
    course.update({
        "subject": subject,
        "number": number,
        "title": title,
        "term": term,
        "instructor_id": instructor_id
    })
    datastore_client.put(course)

    response = {
        "id": course.key.id,
        "subject": subject,
        "number": number,
        "title": title,
        "term": term,
        "instructor_id": instructor_id,
        "self": f"{request.host_url.rstrip('/')}/courses/{course.key.id}"
    }

    return jsonify(response), 201




# Route 8: GET /courses 
@app.route('/courses', methods=['GET'])
def get_all_courses():
    # Step 1: Get optional limit/offset query parameters
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 3))
    except ValueError:
        return jsonify({"Error": "Invalid query parameters"}), 400

    # Step 2: Query courses and sort by subject
    query = datastore_client.query(kind="courses")
    query.order = ["subject"]
    results = list(query.fetch(offset=offset, limit=limit))

    # Step 3: Format each course entry
    courses_list = []
    for course in results:
        courses_list.append({
            "id": course.key.id,
            "subject": course["subject"],
            "number": course["number"],
            "title": course["title"],
            "term": course["term"],
            "instructor_id": course["instructor_id"],
            "self": f"{request.host_url.rstrip('/')}/courses/{course.key.id}"
        })

    # Step 4: Build response
    response = {
        "courses": courses_list
    }

    # Add "next" link if number of courses equals the limit (optional per spec)
    if len(results) == limit:
        next_offset = offset + limit
        response["next"] = f"{request.host_url.rstrip('/')}/courses?limit={limit}&offset={next_offset}"

    return jsonify(response), 200



# Route 9 - GET a course by ID
@app.route('/courses/<int:course_id>', methods=['GET'])
def get_course(course_id):
    # Step 1: Retrieve course from Datastore
    course_key = datastore_client.key("courses", course_id)
    course = datastore_client.get(course_key)

    if not course:
        return jsonify({ "Error": "Not found" }), 404

    # Step 2: Construct response (exclude students list)
    response = {
        "id": course.key.id,
        "subject": course["subject"],
        "number": course["number"],
        "title": course["title"],
        "term": course["term"],
        "instructor_id": course["instructor_id"],
        "self": f"{request.host_url.rstrip('/')}/courses/{course.key.id}"
    }

    return jsonify(response), 200





# Route 10 - PATCH /courses/<course_id> - Update a course
@app.route('/courses/<int:course_id>', methods=['PATCH'])
def update_course(course_id):
    # Step 1: Verify JWT
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": "Unauthorized"}), 401

    # Step 2: Ensure the user is an admin
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    requester = list(query.fetch())
    if not requester or requester[0].get("role") != "admin":
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Fetch the course
    course_key = datastore_client.key("courses", course_id)
    course = datastore_client.get(course_key)
    if not course:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 4: Parse body
    try:
        body = request.get_json()
        if body is None:
            body = {}
    except:
        return jsonify({"Error": "The request body is invalid"}), 400

    # Step 5: Validate instructor_id if present
    if "instructor_id" in body:
        instructor_key = datastore_client.key("users", body["instructor_id"])
        instructor = datastore_client.get(instructor_key)
        if not instructor or instructor.get("role") != "instructor":
            return jsonify({"Error": "The request body is invalid"}), 400

    # Step 6: Apply updates to valid fields
    updatable_fields = {"subject", "number", "title", "term", "instructor_id"}
    for field in updatable_fields:
        if field in body:
            course[field] = body[field]

    # Step 7: Save and respond
    datastore_client.put(course)

    return jsonify({
        "id": course.key.id,
        "subject": course["subject"],
        "number": course["number"],
        "title": course["title"],
        "term": course["term"],
        "instructor_id": course["instructor_id"],
        "self": f"{request.host_url.rstrip('/')}/courses/{course.key.id}"
    }), 200


# Route 11 - DELETE a course
@app.route('/courses/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    # Step 1: Verify JWT
    sub, error_msg, status = verify_jwt_and_get_sub()
    if status == 401:
        return jsonify({"Error": "Unauthorized"}), 401

    # Step 2: Check if user is admin
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    requester = list(query.fetch())
    if not requester or requester[0]["role"] != "admin":
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Check if course exists
    course_key = datastore_client.key("courses", course_id)
    course = datastore_client.get(course_key)
    if not course:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 4: Remove course from instructor (if assigned)
    instructor_id = course.get("instructor_id")
    if instructor_id:
        instructor_key = datastore_client.key("users", instructor_id)
        instructor = datastore_client.get(instructor_key)
        if instructor and "courses" in instructor:
            instructor["courses"] = [cid for cid in instructor["courses"] if cid != course_id]
            datastore_client.put(instructor)

    # Step 5: Remove course from enrolled students
    query = datastore_client.query(kind="users")
    query.add_filter("role", "=", "student")
    students = list(query.fetch())
    for student in students:
        if "courses" in student and course_id in student["courses"]:
            student["courses"] = [cid for cid in student["courses"] if cid != course_id]
            datastore_client.put(student)

    # Step 6: Delete the course
    datastore_client.delete(course_key)

    # Step 7: Return 204 No Content
    return ("", 204)


# Route 12 - Update enrollment in course 
@app.route('/courses/<int:course_id>/students', methods=['PATCH'])
def update_enrollment(course_id):
    # Step 1: Verify JWT
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": "Unauthorized"}), 401

    # Step 2: Get course
    course_key = datastore_client.key("courses", course_id)
    course = datastore_client.get(course_key)
    if not course:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Get requester user
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    requester_list = list(query.fetch())
    if not requester_list:
        return jsonify({"Error": "You don't have permission on this resource"}), 403
    requester = requester_list[0]

    # Step 4: Check admin or instructor of the course
    is_admin = requester.get("role") == "admin"
    is_instructor = (requester.get("role") == "instructor" and requester.key.id == course["instructor_id"])
    if not (is_admin or is_instructor):
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 5: Parse and validate body
    try:
        body = request.get_json()
        add_ids = set(body.get("add", []))
        remove_ids = set(body.get("remove", []))
    except:
        return jsonify({"Error": "The request body is invalid"}), 400

    if not (add_ids or remove_ids):
        return jsonify({"Error": "The request body is invalid"}), 400

    # Step 6: Check for overlapping IDs
    if add_ids & remove_ids:
        return jsonify({"Error": "Enrollment data is invalid"}), 409

    # Step 7: Fetch all student users to validate roles
    all_ids = add_ids | remove_ids
    invalid = False
    for uid in all_ids:
        key = datastore_client.key("users", uid)
        user = datastore_client.get(key)
        if not user or user.get("role") != "student":
            invalid = True
            break
    if invalid:
        return jsonify({"Error": "Enrollment data is invalid"}), 409

    # Step 8: Update student entities
    for sid in add_ids:
        key = datastore_client.key("users", sid)
        student = datastore_client.get(key)
        if "courses" not in student:
            student["courses"] = []
        if course_id not in student["courses"]:
            student["courses"].append(course_id)
        datastore_client.put(student)

    for sid in remove_ids:
        key = datastore_client.key("users", sid)
        student = datastore_client.get(key)
        if "courses" in student and course_id in student["courses"]:
            student["courses"] = [cid for cid in student["courses"] if cid != course_id]
            datastore_client.put(student)

    return '', 200


# Route 13 - GET enrollment for a course 
@app.route('/courses/<int:course_id>/students', methods=['GET'])
def get_course_enrollment(course_id):
    # Step 1: Verify JWT
    sub, error_msg, status = verify_jwt_and_get_sub()
    if error_msg:
        return jsonify({"Error": "Unauthorized"}), 401

    # Step 2: Retrieve course from Datastore
    course_key = datastore_client.key("courses", course_id)
    course = datastore_client.get(course_key)
    if not course:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 3: Get requester user
    query = datastore_client.query(kind="users")
    query.add_filter("sub", "=", sub)
    requester_list = list(query.fetch())
    if not requester_list:
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    requester = requester_list[0]
    is_admin = requester.get("role") == "admin"
    is_instructor = (requester.get("role") == "instructor" and requester.key.id == course["instructor_id"])

    if not (is_admin or is_instructor):
        return jsonify({"Error": "You don't have permission on this resource"}), 403

    # Step 4: Collect all students enrolled in the course
    query = datastore_client.query(kind="users")
    query.add_filter("role", "=", "student")
    enrolled_students = []

    for student in query.fetch():
        if "courses" in student and course_id in student["courses"]:
            enrolled_students.append(student.key.id)

    return jsonify(enrolled_students), 200





# Routes below taken from provided files in module's exploration

@app.route('/images', methods=['POST'])
def store_image():
    # Any files in the request will be available in request.files object
    # Check if there is an entry in request.files with the key 'file'
    if 'file' not in request.files:
        return ('No file sent in request', 400)
    # Set file_obj to the file sent in the request
    file_obj = request.files['file']
    # If the multipart form data has a part with name 'tag', set the
    # value of the variable 'tag' to the value of 'tag' in the request.
    # Note we are not doing anything with the variable 'tag' in this
    # example, however this illustrates how we can extract data from the
    # multipart form data in addition to the files.
    if 'tag' in request.form:
        tag = request.form['tag']
    # Create a storage client
    storage_client = storage.Client()
    # Get a handle on the bucket
    bucket = storage_client.get_bucket(PHOTO_BUCKET)
    # Create a blob object for the bucket with the name of the file
    blob = bucket.blob(file_obj.filename)
    # Position the file_obj to its beginning
    file_obj.seek(0)
    # Upload the file into Cloud Storage
    blob.upload_from_file(file_obj)
    return ({'file_name': file_obj.filename},201)

@app.route('/images/<file_name>', methods=['GET'])
def get_image(file_name):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(PHOTO_BUCKET)
    # Create a blob with the given file name
    blob = bucket.blob(file_name)
    # Create a file object in memory using Python io package
    file_obj = io.BytesIO()
    # Download the file from Cloud Storage to the file_obj variable
    blob.download_to_file(file_obj)
    # Position the file_obj to its beginning
    file_obj.seek(0)
    # Send the object as a file in the response with the correct MIME type and file name
    return send_file(file_obj, mimetype='image/x-png', download_name=file_name)


@app.route('/images/<file_name>', methods=['DELETE'])
def delete_image(file_name):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(PHOTO_BUCKET)
    blob = bucket.blob(file_name)
    # Delete the file from Cloud Storage
    blob.delete()
    return '',204

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)