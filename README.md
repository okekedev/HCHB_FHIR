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

4. Copy `.env.example` to `.env` and add your credentials.

## Usage

```bash
cd apis/patients
python patients.py
```

## Use Cases

Patient-centric queries that demonstrate common workflows.

<details>
<summary><strong>Get Patient Payor</strong> ✅</summary>

Retrieves the payor organization for a patient via the Account resource.

### Flow

```
Patient → Account (by subject) → guarantor → Organization (Payor)
```

### Usage

```bash
python use_cases/get_patient_payor.py
python use_cases/get_patient_payor.py --patient_id <patient_id>
```

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| --patient_id | Patient FHIR ID | Fetches sample patient if not provided |

### Output

Returns payor details including ID, name, type, phone, and address.

</details>

## APIs

<details>
<summary><strong>Patient API</strong></summary>

### Search Parameters

| Parameter | Description |
|-----------|-------------|
| _id | Logical resource ID |
| identifier | Patient identifier (MRN) |
| active | Status filter (true/false) |
| name | Full name search |
| family | Last name |
| given | First name |
| telecom | Phone number |
| email | Email address |
| gender | male, female, other, unknown |
| birthdate | Date of birth |
| address | General address search |
| address-city | City |
| address-state | State |
| address-postalcode | ZIP code |
| organization | Managing organization reference |

### Defaults

| Setting | Value |
|---------|-------|
| page_size | 100 records per page |
| max_pages | 1 |
| timeout | 120 seconds |
| active | true (only active patients) |

### Notes

- This API does not support generic date filtering
- Maximum of 5000 records can be returned per request regardless of pagination

</details>

## Project Structure

```
HCHB_FHIR/
├── apis/
│   └── patients/
│       ├── patients.py
│       └── samples/         # Output files (gitignored)
├── use_cases/
│   ├── get_patient_payor.py
│   └── output/              # Output files (gitignored)
├── .env                     # Credentials (not tracked)
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## Disclaimer

No EPHI (Electronic Protected Health Information) is stored or maintained in this repository. This repo is for reference only. The goal of this project is to support interoperability and provide patients with the most optimal care.

## License

See [LICENSE](LICENSE) for details.
