# HCHB_FHIR_APIS

FHIR API integration project for HCHB.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

2. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Unix/macOS: `source venv/bin/activate`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and add your credentials:


## Usage

Run a patient API sample:
```bash
cd apis/patients
python patients.py
```

This fetches one page of patients and exports to `samples/` folder as JSON.

## Project Structure

```
HCHB_FHIR/
├── apis/
│   └── patients/
│       ├── patients.py      # Patient API functions
│       ├── parameters.txt   # Available search parameters
│       └── samples/         # Output files (gitignored)
├── .env                     # Environment variables (not tracked)
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## Configuration

Environment variables in `.env.example'

## Defaults

- `page_size`: 100 records per page
- `max_pages`: 1
- `timeout`: 120 seconds
- `active`: true (only active patients)

See `apis/patients/parameters.txt` for available search parameters.

## Notes

- Maximum of 5000 records can be returned per request regardless of pagination
- Sample outputs are excluded from version control
