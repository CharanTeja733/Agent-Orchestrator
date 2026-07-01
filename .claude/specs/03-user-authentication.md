# Feature 3: User Authentication (Register/Login/JWT)

## 1. Overview

Implement the complete authentication system for the HR Q&A Agent. Users can register, login, receive JWT tokens, and access protected endpoints. This establishes **identity and security** for the entire application.

All future features (sessions, chat, feedback) depend on knowing who the user is.

---

## 2. Depends on

- **Feature 1: Project Setup & Docker Environment** — services must be running
- **Feature 2: Database Schema & Migrations** — users table must exist with seed data

---

## 3. Routes

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/auth/register` | No | Create new user account |
| `POST` | `/auth/login` | No | Authenticate and receive JWT |
| `GET` | `/auth/me` | Yes (JWT) | Get current user profile |
| `POST` | `/auth/refresh` | Yes (JWT) | Refresh expiring token |

---

## 4. Route Specifications

### A. `POST /auth/register`

**Request Body:**
```json
{
  "email": "newuser@company.com",
  "password": "SecurePass123!",
  "full_name": "New User",
  "role": "employee",
  "department": "engineering"
}
```

**Validation Rules:**
- `email`: Must be valid email format, must not already exist in DB
- `password`: Minimum 8 characters, at least 1 uppercase, 1 lowercase, 1 digit
- `full_name`: Minimum 2 characters, maximum 255 characters
- `role`: Must be one of `employee`, `manager`, `hr_admin`
- `department`: Non-empty string, maximum 100 characters

**Success Response (201):**
```json
{
  "message": "User registered successfully",
  "user": {
    "id": "uuid-string",
    "email": "newuser@company.com",
    "full_name": "New User",
    "role": "employee",
    "department": "engineering",
    "is_active": true,
    "created_at": "2026-07-01T10:00:00Z"
  }
}
```

**Error Responses:**
- `409` — Email already registered
- `422` — Validation error (invalid email, weak password, etc.)

---

### B. `POST /auth/login`

**Request Body:**
```json
{
  "email": "john@company.com",
  "password": "john123"
}
```

**Success Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid-string",
    "email": "john@company.com",
    "full_name": "John Doe",
    "role": "employee",
    "department": "engineering"
  }
}
```

**Error Responses:**
- `401` — Invalid email or password
- `403` — Account is deactivated

---

### C. `GET /auth/me`

**Headers:** `Authorization: Bearer <access_token>`

**Success Response (200):**
```json
{
  "id": "uuid-string",
  "email": "john@company.com",
  "full_name": "John Doe",
  "role": "employee",
  "department": "engineering",
  "is_active": true,
  "created_at": "2026-07-01T10:00:00Z",
  "updated_at": "2026-07-01T10:00:00Z"
}
```

**Error Responses:**
- `401` — Invalid or expired token
- `403` — Account deactivated

---

### D. `POST /auth/refresh`

**Headers:** `Authorization: Bearer <refresh_token>`

**Success Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Error Responses:**
- `401` — Invalid or expired refresh token

---

## 5. Token Specifications

### Access Token

| Claim | Value |
|-------|-------|
| `sub` | User UUID |
| `email` | User email |
| `role` | User role |
| `department` | User department |
| `type` | `"access"` |
| `exp` | Now + 1 hour |
| `iat` | Issued at time |
| `jti` | Unique token ID (UUID) |

### Refresh Token

| Claim | Value |
|-------|-------|
| `sub` | User UUID |
| `type` | `"refresh"` |
| `exp` | Now + 7 days |
| `iat` | Issued at time |
| `jti` | Unique token ID (UUID) |

### Token Configuration

- Algorithm: HS256
- Secret key: From `config.SECRET_KEY`
- Access token expiry: 60 minutes
- Refresh token expiry: 7 days

---

## 6. Files to Create

### A. `backend/app/auth/__init__.py`

- Empty file (makes `auth` a Python package)

---

### B. `backend/app/auth/utils.py`

Token and password utility functions:

#### `hash_password(password: str) -> str`
- Uses `passlib` with bcrypt scheme
- Returns hashed password string
- Auto-generates salt

#### `verify_password(plain_password: str, hashed_password: str) -> bool`
- Uses `passlib` to verify password against hash
- Returns True/False
- Constant-time comparison (built into passlib)

#### `create_access_token(user_id: str, email: str, role: str, department: str) -> str`
- Creates JWT with claims from section 5
- Uses `python-jose` library
- Sets `type: "access"`
- Returns encoded JWT string

#### `create_refresh_token(user_id: str) -> str`
- Creates JWT with claims from section 5
- Sets `type: "refresh"`
- Returns encoded JWT string

#### `decode_token(token: str) -> dict`
- Decodes and verifies JWT
- Returns payload dict
- Raises `JWTError` on invalid/expired token
- Validates signature using SECRET_KEY

#### `verify_token_type(payload: dict, expected_type: str) -> bool`
- Checks `type` claim matches expected value
- Prevents refresh tokens from being used as access tokens

---

### C. `backend/app/auth/dependencies.py`

FastAPI dependency functions:

#### `get_current_user(token: str = Depends(oauth2_scheme)) -> User`
- Decodes JWT from Authorization header
- Verifies token type is "access"
- Extracts user_id from `sub` claim
- Queries database for user
- Raises `401` if token invalid or expired
- Raises `401` if user not found
- Raises `403` if user is deactivated (`is_active = False`)
- Returns User ORM object

#### `get_current_active_user(current_user: User = Depends(get_current_user)) -> User`
- Wraps `get_current_user`
- Explicitly checks `is_active` flag
- Returns active user

#### `oauth2_scheme`
- Instance of `OAuth2PasswordBearer`
- Token URL: `/auth/login`
- Extracts Bearer token from Authorization header

---

### D. `backend/app/auth/router.py`

FastAPI router with all auth endpoints:

#### Router Setup
- Prefix: `/auth`
- Tags: `["Authentication"]`
- Import and use dependencies and utilities

#### `POST /auth/register` handler
- Validate request body using Pydantic schema
- Check if email already exists → 409 if yes
- Hash password using `hash_password()`
- Insert new user into database
- Return 201 with user details (excluding password hash)

#### `POST /auth/login` handler
- Validate request body
- Query user by email
- If user not found → 401 "Invalid email or password"
- If user is deactivated → 403 "Account is deactivated"
- Verify password using `verify_password()`
- If password wrong → 401 "Invalid email or password"
- Generate access token and refresh token
- Return 200 with tokens and user info

#### `GET /auth/me` handler
- Get current user via `get_current_user` dependency
- Return user profile

#### `POST /auth/refresh` handler
- Extract refresh token from Authorization header
- Decode and verify token
- Verify token type is "refresh"
- Query user by `sub` claim
- If user not found or deactivated → 401
- Generate new access token only
- Return 200 with new access token

---

### E. `backend/app/auth/schemas.py`

Pydantic schemas specific to authentication:

#### `UserRegister`
```python
class UserRegister(BaseModel):
    email: EmailStr
    password: str (min_length=8, validation for complexity)
    full_name: str (min_length=2, max_length=255)
    role: str (must be in UserRole enum)
    department: str (min_length=1, max_length=100)
```

#### `UserLogin`
```python
class UserLogin(BaseModel):
    email: EmailStr
    password: str
```

#### `TokenResponse`
```python
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
```

#### `RefreshResponse`
```python
class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
```

---

## 7. Changes to Existing Files

### A. `backend/app/main.py`

Add auth router:
```python
from app.auth.router import router as auth_router
app.include_router(auth_router)
```

Add exception handlers:
- `401 Unauthorized` → JSON response with detail message
- `403 Forbidden` → JSON response with detail message
- `JWTError` → 401 response

---

### B. `backend/app/schemas.py`

Add/update schemas:

- **`UserResponse`**: id, email, full_name, role, department, is_active, created_at
- **`UserRole`** enum: `employee`, `manager`, `hr_admin`
- Ensure these are importable by auth module

---

### C. `backend/app/models.py`

Ensure `User` model has:
- `is_active` column with default `True`
- `updated_at` column with auto-update on change

---

## 8. Files to Change

- `backend/app/main.py` — add auth router and exception handlers
- `backend/app/schemas.py` — ensure UserResponse and UserRole are defined
- `backend/app/models.py` — ensure User model is complete

---

## 9. Files to Create

- `backend/app/auth/__init__.py`
- `backend/app/auth/utils.py`
- `backend/app/auth/dependencies.py`
- `backend/app/auth/router.py`
- `backend/app/auth/schemas.py`

---

## 10. Dependencies

All already in `requirements.txt` from Feature 1:
- `python-jose[cryptography]` — JWT creation and verification
- `passlib[bcrypt]` — Password hashing
- `pydantic` — Request validation (EmailStr from pydantic[email])
- `python-multipart` — Form data parsing (for OAuth2 password flow)

**Add to requirements.txt:**
- `pydantic[email]` — for EmailStr validation

---

## 11. Rules for Implementation

- **Never log or return password hashes** in responses or logs
- Use **constant-time comparison** for password verification (built into passlib)
- **Never store plaintext passwords** — hash before any database operation
- Use `EmailStr` from pydantic for email validation
- Token validation must check:
  - Signature validity
  - Expiration (`exp` claim)
  - Token type (`type` claim for refresh vs access)
  - User existence and active status
- Return **generic error messages** for login failures (don't reveal if email exists or password is wrong — use same message for both)
- Refresh tokens can only generate new access tokens, not new refresh tokens
- All protected endpoints use `get_current_user` dependency
- Password validation rules must be enforced server-side (not client-side only)
- Rate limiting not required for this feature (add in Feature 11 if needed)

---

## 12. Security Rules

- Access token expiry: 1 hour maximum
- Refresh token expiry: 7 days maximum
- SECRET_KEY must be at least 32 characters (validate on startup)
- All tokens signed with HS256 algorithm
- JWT `sub` claim must be the user's UUID (not email — UUID is immutable)
- Token `jti` claim should be unique (use UUID)
- Authentication failures must be logged with timestamp and attempt source
- Do not include sensitive user data in JWT payload beyond what's specified

---

## 13. Expected Behavior

### Registration flow:
1. User sends valid registration data → 201 with user profile
2. User sends duplicate email → 409 error
3. User sends weak password → 422 validation error
4. User sends invalid email format → 422 validation error

### Login flow:
1. User sends valid credentials → 200 with access + refresh tokens
2. User sends wrong password → 401 "Invalid email or password"
3. User sends non-existent email → 401 "Invalid email or password"
4. User is deactivated → 403 "Account is deactivated"

### Authenticated request flow:
1. Valid token in Authorization header → user object available in endpoint
2. Expired token → 401 "Token has expired"
3. Invalid token → 401 "Could not validate credentials"
4. Missing Authorization header → 401 "Not authenticated"

### Token refresh flow:
1. Valid refresh token → 200 with new access token
2. Access token used instead of refresh token → 401 "Invalid token type"
3. Expired refresh token → 401 "Token has expired"

---

## 14. Error Handling Expectations

| Scenario | HTTP Status | Message |
|----------|-------------|---------|
| Email already registered | 409 | "A user with this email already exists" |
| Invalid email format | 422 | "Invalid email format" |
| Weak password | 422 | "Password must be at least 8 characters with uppercase, lowercase, and digit" |
| Invalid credentials | 401 | "Invalid email or password" |
| Account deactivated | 403 | "Account is deactivated. Contact HR administrator." |
| Expired token | 401 | "Token has expired" |
| Invalid token | 401 | "Could not validate credentials" |
| Missing auth header | 401 | "Not authenticated" |
| Wrong token type | 401 | "Invalid token type" |
| User not found (in token) | 401 | "User not found" |

---

## 15. Verification Steps

After implementation, test using curl or HTTP client:

```bash
# 1. Register a new user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@company.com","password":"TestPass123!","full_name":"Test User","role":"employee","department":"engineering"}'

# 2. Login with seeded user
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}'

# 3. Get current user (replace TOKEN with access_token from login)
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer TOKEN"

# 4. Refresh token (replace TOKEN with refresh_token from login)
curl -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer REFRESH_TOKEN"

# 5. Test duplicate registration
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"TestPass123!","full_name":"Test","role":"employee","department":"engineering"}'

# 6. Test wrong password
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"wrongpassword"}'
```

---

## 16. Definition of Done

- [ ] `POST /auth/register` creates user with hashed password
- [ ] `POST /auth/register` rejects duplicate emails (409)
- [ ] `POST /auth/register` validates password strength (422)
- [ ] `POST /auth/login` returns valid JWT tokens for correct credentials
- [ ] `POST /auth/login` returns 401 for incorrect credentials
- [ ] `POST /auth/login` returns 403 for deactivated users
- [ ] `GET /auth/me` returns user profile with valid token
- [ ] `GET /auth/me` returns 401 with invalid/expired token
- [ ] `POST /auth/refresh` returns new access token with valid refresh token
- [ ] `POST /auth/refresh` rejects access tokens used as refresh tokens
- [ ] Passwords are bcrypt hashed (verify in Adminer: hashes start with `$2b$`)
- [ ] Password hashes are never returned in API responses
- [ ] Seeded users from Feature 2 can login successfully
- [ ] Access tokens expire after 1 hour
- [ ] Refresh tokens expire after 7 days
- [ ] All error messages are user-friendly (no stack traces)
- [ ] Auth endpoints are documented in Swagger UI (`/docs`)