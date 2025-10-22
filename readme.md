

# 🧾 Credit Card Statement Parser

A Python project that extracts key details from **credit card statements** using two approaches:

1. **Regex Parser** – for text-based PDFs.
2. **OCR Parser** – for scanned or image-based PDFs.

---

## ⚙️ Features

* Supports multiple issuers (ICICI, IDFC, HDFC, CITI, etc.)
* Extracts:

  * Cardholder Name
  * Last 4 Digits
  * Billing Period
  * Payment Due Date
  * Total Amount Due
* Auto-detects issuer
* JSON / text output
* Optional debug text files for OCR verification

---

## 🧩 Installation

```bash
git clone https://github.com/yourusername/credit-card-parser.git
cd credit-card-parser
python -m venv venv
venv\Scripts\activate     # or source venv/bin/activate
```

### Dependencies

Regex parser:

```bash
pip install PyPDF2 pandas
```

OCR parser:

```bash
pip install pdf2image pytesseract pillow opencv-python
```

---

## 🧰 Setup (OCR Parser)

### Poppler (for `pdf2image`)

* Download from [Poppler Windows Builds](https://github.com/oschwartz10612/poppler-windows/releases/)
* Add `<poppler>\Library\bin` to PATH or pass `poppler_path` in code.

### Tesseract OCR

* Install from [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
* Add `C:\Program Files\Tesseract-OCR` to PATH or define:

  ```python
  pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
  ```

---

## ▶️ Usage

### Regex Parser

```bash
python parser.py
```

### OCR Parser

```bash
python ocr_parser_better.py
```

---

## 📄 Output Example

```json
[
  {
    "issuer": "ICICI",
    "cardholder_name": "Ashok",
    "last_4_digits": "2004",
    "billing_period": "15/02/2019 to 14/03/2019",
    "payment_due_date": "14/03/2019",
    "total_amount_due": "1922.00",
    "used_ocr": true,
    "source_file": "icici_statement.pdf"
  }
]
```

---

## 🧠 Comparison

| Feature               | Regex Parser | OCR Parser        |
| --------------------- | ------------ | ----------------- |
| Works on Scanned PDFs | ❌            | ✅                 |
| Accuracy (text PDFs)  | ✅            | ⚙️ Depends on OCR |
| Speed                 | ⚡ Fast       | 🕒 Slower         |
| Setup Effort          | Low          | Moderate          |

---

## 📚 Future Scope

* Transaction table extraction
* Combined hybrid (regex + OCR) pipeline
* LLM-based auto field mapping


