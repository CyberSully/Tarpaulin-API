# Tarpaulin Course Management API

The **Tarpaulin Course Management Tool** is a RESTful API built using Python 3 and Google App Engine. It provides role-based access to manage users, courses, enrollments, and profile avatars. The system supports authentication via Auth0 JWTs and uses Google Cloud Datastore and Cloud Storage for persistent data and file storage.

## Overview

This project was developed as a cloud application portfolio project for CS 493. It demonstrates a fully functional API deployment on GCP using:

- Google App Engine (GAE)
- Cloud Datastore (NoSQL)
- Cloud Storage for file uploads
- Auth0 for authentication
- Postman and Newman for automated testing

The API supports multiple user roles (`admin`, `instructor`, and `student`) with permissions and access controls enforced at the route level.

---

## Endpoints

All endpoints are protected via JWT (Bearer token). Routes are scoped by user role, and validation rules ensure proper access and data consistency.

### Users

- `POST /users`  
  Create a new user profile.

- `GET /users/<user_id>`  
  Retrieve a specific user's information (restricted by role).

- `PATCH /users/<user_id>`  
  Update a user's role (admin only).

- `DELETE /users/<user_id>`  
  Delete a user (admin only).

### Avatars

- `POST /users/<user_id>/avatar`  
  Upload an avatar image (PNG only, 5MB max).

- `GET /users/<user_id>/avatar`  
  Retrieve a user's avatar.

- `DELETE /users/<user_id>/avatar`  
  Remove a user's avatar.

### Courses

- `POST /courses`  
  Create a new course (admin or instructor).

- `GET /courses/<course_id>`  
  Get details about a course (restricted by role).

- `PATCH /courses/<course_id>`  
  Update course info (admin or the instructor who owns it).

- `DELETE /courses/<course_id>`  
  Delete a course (admin only).

- `PATCH /courses/<course_id>/students`  
  Enroll or disenroll students (admin or course instructor).

- `GET /courses/<course_id>/students`  
  Get the list of enrolled student IDs (admin or course instructor).

---

## Testing

The project includes a full [Postman collection](assignment6.postman_collection2.json) to validate all API behavior.

### Local Testing with Newman

To run the test suite from the command line:

```bash
newman run assignment6.postman_collection2.json -e assignment6.postman_environment.json
