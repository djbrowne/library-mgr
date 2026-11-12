# Tanager Library Management System

A web-based library management application built with Python (Flask) and SQLite3, tailored for small-to-medium physical book collections. Designed for rapid keyboard navigation, barcode scanner support, automated metadata and cover retrieval, and administrative reconciliation.

---

## 1. Quick Start

### 1.1. Prerequisites
- Ubuntu Linux (or any modern Linux distribution)
- Python 3.10+
- Internet access (for initial Open Library / Google Books metadata and cover fetching)

### 1.2. Installation & Setup
```bash
# 1. Clone the repository and enter the directory
cd library-mgr

# 2. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize the SQLite3 database schema & seed sample books and users
python cli.py init-db
python cli.py seed-sample

# 5. (Optional) Bulk import users from CSV
python cli.py import-users sample_users.csv
```

### 1.3. Running the Web Application
```bash
source .venv/bin/activate
python run.py
```
Open your browser and navigate to: **`http://localhost:5000`**

### 1.4. Running the Automated Test Suite
```bash
source .venv/bin/activate
pytest -v
```

---

## 2. Key System Specifications & Business Rules

### 2.1. User Identification & Role Management
- **User Identity**: Every user has a unique **4-digit numeric ID** (e.g., `0001`, `1001`, `1042`).
- **User Attributes**:
  - `user_id`: 4-digit string (Primary Key)
  - `name`: Full name
  - `email`: Optional email address (used for return/overdue reminders)
  - `is_admin`: Boolean flag indicating administrator privileges
  - `notes`: Administrative notes
  - `is_active`: Boolean status flag
- **User Provisioning**:
  1. **Admin Web Interface**: Direct user management UI (`/admin/users`) to create, toggle admin rights, or deactivate members.
  2. **CLI Bulk CSV Import**:
     ```bash
     python cli.py import-users sample_users.csv
     ```
     Format: `name,id,email,notes`
- **Admin Access Control**: Privileges are controlled via `is_admin` in the user table. Admins can reconcile items, change conditions, deactivate lost books, and manage user accounts.

### 2.2. Book Tracking & Multiple Copies (`ISBN-1`, `ISBN-2`)
- **Metadata Fetching**: Automatic lookup via Open Library & Google Books API fetching Title, Author, Description, Publisher, and cover art. Covers are permanently stored locally (`static/covers/<isbn>.jpg`).
- **Copy Suffixes**: Multiple copies of the same ISBN are tracked using sequential suffixes: `9780132350884-1`, `9780132350884-2`, etc.
- **Copy Auto-Resolution**: When scanning or entering a base ISBN on check-in or check-out, the system automatically resolves the copy if only one is available or borrowed.

### 2.3. Circulation & Loan Rules
- **Loan Duration**: Default loan duration is **60 days** (tracked for reporting and overdue calculation).
- **Check-Out Station** (`/circulation/checkout`):
  1. Scan/enter 4-digit User ID.
  2. Scan/enter Book ISBN or Copy ID.
  3. Records checkout timestamp and calculated due date (+60 days).
- **Check-In Station** (`/circulation/checkin`):
  1. Scan/enter Book ISBN or Copy ID.
  2. Records return timestamp and prompts user to place the book on the library room shelf or in the reservation bin.
- **Holds & Reservations** (`/circulation/holds`):
  - Users can reserve books currently checked out.
  - Copies transition to `borrowed_and_on_hold`, and upon check-in to `on_hold`.

### 2.4. Admin Reconciliation & Deactivation
- **Reconciliation Dashboard** (`/admin/reconcile`):
  - Allows staff to adjust book status (`available`, `borrowed`, `on_hold`, `lost`, `removed`).
  - Modify book condition (`new`, `good`, `damaged`).
  - Update physical shelf/room location.
- **Deactivation (Lost / Removed Books)**:
  - Administrators can soft-deactivate books. Deactivated books cannot be circulated, but **100% of past loans and audit history are permanently preserved**.

### 2.5. Permanent Audit Trail & Privacy
- **Audit Logging** (`/reports/audit-log`): Every state change, registration, checkout, return, and reconciliation is recorded permanently with user IDs and timestamps.
- **Privacy Compliance**: In accordance with library privacy standards, **user search queries are never recorded in audit logs**.

---

## 3. Database Schema Overview (SQLite3)

```
USERS
  ├── user_id (CHAR(4), PK)
  ├── name (VARCHAR)
  ├── email (VARCHAR, Optional)
  ├── is_admin (BOOLEAN, Default False)
  ├── notes (TEXT)
  ├── is_active (BOOLEAN, Default True)
  └── created_at (TIMESTAMP)

TITLES (Bibliographic Metadata)
  ├── isbn (VARCHAR, PK)
  ├── title (VARCHAR)
  ├── authors (VARCHAR)
  ├── description (TEXT)
  ├── publisher (VARCHAR)
  ├── publish_year (VARCHAR)
  ├── cover_image_path (VARCHAR)
  └── created_at (TIMESTAMP)

BOOK_COPIES (Physical Inventory Items)
  ├── copy_id (VARCHAR, PK) - e.g. "9780132350884-1"
  ├── isbn (VARCHAR, FK -> TITLES.isbn)
  ├── copy_number (INTEGER) - 1, 2, ...
  ├── condition (VARCHAR) - "new", "good", "damaged"
  ├── status (VARCHAR) - "available", "borrowed", "on_hold", "lost", "removed"
  ├── location (VARCHAR) - Room / Shelf code
  ├── registered_by (CHAR(4), FK -> USERS.user_id)
  ├── registered_at (TIMESTAMP)
  ├── last_reconciled_at (TIMESTAMP)
  └── notes (TEXT)

LOANS (Circulation Records)
  ├── loan_id (INTEGER, PK Auto)
  ├── copy_id (VARCHAR, FK -> BOOK_COPIES.copy_id)
  ├── user_id (CHAR(4), FK -> USERS.user_id)
  ├── checkout_date (TIMESTAMP)
  ├── due_date (TIMESTAMP)
  ├── returned_date (TIMESTAMP, Nullable)
  ├── return_condition (VARCHAR)
  └── status (VARCHAR) - "active", "returned", "lost"

HOLDS (Reservations)
  ├── hold_id (INTEGER, PK Auto)
  ├── isbn (VARCHAR, FK -> TITLES.isbn)
  ├── user_id (CHAR(4), FK -> USERS.user_id)
  ├── placed_at (TIMESTAMP)
  └── status (VARCHAR) - "waiting", "ready", "fulfilled", "cancelled"

AUDIT_LOGS (Permanent Event History)
  ├── log_id (INTEGER, PK Auto)
  ├── copy_id (VARCHAR)
  ├── isbn (VARCHAR)
  ├── user_id (CHAR(4))
  ├── action (VARCHAR) - "REGISTER", "CHECKOUT", "CHECKIN", "RECONCILE", "DEACTIVATE"
  ├── previous_state (TEXT)
  ├── new_state (TEXT)
  ├── notes (TEXT)
  └── timestamp (TIMESTAMP)
```

---

## 4. Hardware & Barcode Scanning Support

- **Hardware Barcode Scanners (USB/Bluetooth HID)**: Input fields use autofocus and Enter-key submission handlers, allowing rapid one-click checkout and checkin.
- **Integrated Camera Barcode Scanning**:
  - Live WebRTC camera feed streaming from the integrated webcam (`/dev/video0`) with targeting reticle and auto-scanning.
  - Server-side multi-pass image decoding pipeline powered by `pyzbar` and OpenCV (grayscale, CLAHE contrast enhancement, Otsu thresholding, and multi-angle rotation).
  - Works across all browsers without requiring experimental browser flags.
  - Direct Linux host device capture via `/api/capture-camera`.
  - Full **JPG/PNG image file upload and drag-and-drop** support via `/api/scan-barcode` to decode book photos or screenshots.
  - Available across Book Registration, Check-Out, Check-In, and Catalog Search.
  - Automatic audio-visual confirmation beep and field auto-fill.
