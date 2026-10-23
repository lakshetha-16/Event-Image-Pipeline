# Event-Driven Image Classification Pipeline

A student-friendly full-stack project that accepts images, stores them on the local computer, queues processing jobs in SQLite, classifies images with a pretrained MobileNetV2 model, and saves structured JSON metadata. The React dashboard shows image status, job events, basic analytics, and service health.

## Architecture

1. **React + Vite** dashboard (`frontend/`) uploads images and polls the API.
2. **Flask REST API** (`backend/app.py`) validates uploads, calculates SHA-256 checksums, saves image records, and queues a durable event.
3. **Local filesystem storage** saves originals and generated JSON metadata under `backend/data/objects/`. No MinIO, cloud account, access keys, or storage server is required.
4. **SQLite** stores image records, queue events, event logs, and worker heartbeat.
5. **Background worker** consumes queued events, verifies the checksum, runs MobileNetV2/ImageNet inference, and writes metadata.

The queue is SQLite-backed so the demo does not need Redis or RabbitMQ. This is a local single-machine student project, not a high-throughput multi-server deployment.

## Requirements

- Windows 10/11
- Python 3.10–3.12 recommended (TensorFlow compatibility varies by Python version and OS)
- Node.js 20+ and npm
- Internet access for dependency installation and the first MobileNetV2 model-weight download

## Setup — Windows PowerShell

### 1. Set up the backend

Open PowerShell in the project folder:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again. You do not need to configure MinIO or create a `.env` file for the default setup.

### 2. Start the API

In the same backend terminal:

```powershell
python app.py
```

The API runs at `http://127.0.0.1:5000`. Open `http://127.0.0.1:5000/api/health` to check the API and local services. Keep this terminal open.

### 3. Start the classification worker

Open a **second** PowerShell terminal in the project folder:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python event_worker.py
```

The first worker startup loads MobileNetV2 and may download ImageNet weights. Leave the worker terminal open while using the app.

### 4. Start the React dashboard

Open a **third** PowerShell terminal in the project folder:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://127.0.0.1:5173`. Upload a JPG, JPEG, PNG, or WEBP image up to 10 MB. With the worker running, the image should move from pending to processing to completed.

> Run each terminal command from the correct folder. If you already changed directory into `backend`, do not type `cd backend` again in that same terminal.

## Where files are saved

- SQLite database: `backend/data/pipeline.db`
- Uploaded originals: `backend/data/objects/originals/`
- JSON metadata: `backend/data/objects/metadata/`

These local data folders are created automatically. Back them up if you want to keep uploaded images and records.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | API, database, local storage and worker health |
| POST | `/api/images/upload` | Upload one or more images using multipart field `files` |
| GET | `/api/images` | Search/list images; supports `status`, `search`, `page`, `page_size` |
| GET | `/api/images/<id>` | Get one image record |
| GET | `/api/images/<id>/download?inline=1` | View a stored original image |
| GET | `/api/images/<id>/metadata` | Read generated JSON metadata |
| GET | `/api/images/<id>/metadata?download=1` | Download metadata JSON |
| GET | `/api/events` | Recent queue events, logs, and counts |
| GET | `/api/analytics` | Aggregate image-processing metrics |
| GET | `/api/settings` | Safe runtime configuration for display |

## Run tests

From `backend/` with the virtual environment active:

```powershell
python -m unittest discover -s tests -v
```

The core tests use temporary SQLite databases and do not require MinIO or a running model. Full image classification requires compatible TensorFlow dependencies and a first-time model-weight download.

## Security and limitations

- Uploaded files are stored locally on the computer running the backend; this is not cloud storage.
- Uploads are limited by size and file format and validated with Pillow.
- SHA-256 detects accidental changes to stored bytes; it does not encrypt data.
- MobileNetV2 uses ImageNet classes. Predictions can be wrong and are not suitable for authoritative decisions.
- The SQLite queue is for a local demo/single machine. Production deployment would need authentication, rate limiting, a managed queue, monitoring, and stronger deployment controls.
- No image dataset or pretrained model weights are included in this ZIP; TensorFlow may download weights on first startup.

## Project structure

```text
event-image-pipeline/
├── backend/
│   ├── app.py
│   ├── classifier.py
│   ├── config.py
│   ├── database.py
│   ├── event_producer.py
│   ├── event_worker.py
│   ├── metadata_generator.py
│   ├── storage.py
│   ├── validation.py
│   ├── requirements.txt
│   └── tests/
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
```
