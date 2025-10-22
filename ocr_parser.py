import os, re, json, logging
from pdf2image import convert_from_path
import pytesseract
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFilter

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Define project paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATEMENTS_DIR = os.path.join(PROJECT_ROOT, "statements")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
DEBUG_DIR = os.path.join(PROJECT_ROOT, "debug")

# Create necessary directories
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

# ============================================================
# OCR EXTRACTION (always use OCR)
# ============================================================
def preprocess_image_for_ocr(pil_img):
    """Convert PIL image to OpenCV for better OCR accuracy."""
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # Deskew (using image moments)
    coords = np.column_stack(np.where(gray > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    gray = cv2.warpAffine(gray, M, (w, h),
                          flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    # Denoise & Threshold
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray = cv2.adaptiveThreshold(gray, 255,
                                 cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 10)
    pil = Image.fromarray(gray)
    pil = ImageOps.autocontrast(pil)
    pil = pil.filter(ImageFilter.MedianFilter(size=3))
    return pil

def ocr_pdf_to_text(pdf_path, dpi=300):
    """Convert PDF pages to text using OCR only."""
    logging.info(f"OCR extracting: {os.path.basename(pdf_path)}")
    images = convert_from_path(pdf_path, dpi=dpi)
    texts = []
    for i, img in enumerate(images):
        pre = preprocess_image_for_ocr(img)
        text = pytesseract.image_to_string(pre, lang="eng")
        text = re.sub(r"\s+", " ", text)
        texts.append(text.strip())
        logging.info(f"OCR page {i+1}/{len(images)} complete")
    return "\n".join(texts)

# ============================================================
# DETECT ISSUER
# ============================================================
def detect_issuer(text):
    up = text.upper()
    if "ICICI" in up:
        return "ICICI"
    if "IDFC" in up:
        return "IDFC"
    if "HDFC" in up:
        return "HDFC"
    if "CITI" in up or "CITIBANK" in up:
        return "CITI"
    if "AXIS" in up:
        return "AXIS"
    return "UNKNOWN"

# ============================================================
# FIELD EXTRACTION HELPERS
# ============================================================
def extract_fields_generic(text):
    """Fallback generic extraction."""
    data = {
        "cardholder_name": re.search(r"(?:Mr\.|Mrs\.|Ms\.)\s*([A-Z][A-Za-z\s]+)", text),
        "last_4_digits": re.search(r"X{3,4}\s*(\d{4})", text),
        "billing_period": re.search(r"(\d{2}/\d{2}/\d{4})\s*(?:-|to|–)\s*(\d{2}/\d{2}/\d{4})", text),
        "payment_due_date": re.search(r"Due\s*Date[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})", text),
        "total_amount_due": re.search(r"Total\s*Amount\s*Due[:₹r\s]*([0-9,]+\.\d{2}|[0-9,]+)", text)
    }
    for k, v in data.items():
        data[k] = v.group(1).strip() if v else "N/A"
    if data["total_amount_due"] != "N/A":
        data["total_amount_due"] = data["total_amount_due"].replace(",", "")
    return data

def extract_fields_icici(text):
    data = extract_fields_generic(text)
    # refine ICICI-specific
    m = re.search(r"Mr\.?\s*([A-Z][A-Z\s]+)", text, re.IGNORECASE)
    if m:
        data["cardholder_name"] = m.group(1).title().strip()
    return data

def extract_fields_idfc(text):
    data = extract_fields_generic(text)
    m = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    if m and len(m.group(1).split()) >= 2:
        data["cardholder_name"] = m.group(1).strip()
    return data

def extract_fields_hdfc(text):
    data = extract_fields_generic(text)
    return data

def extract_fields_citi(text):
    data = extract_fields_generic(text)
    return data

def extract_fields_axis(text):
    data = extract_fields_generic(text)
    return data

def extract_data_points(text):
    issuer = detect_issuer(text)
    if issuer == "ICICI":
        data = extract_fields_icici(text)
    elif issuer == "IDFC":
        data = extract_fields_idfc(text)
    elif issuer == "HDFC":
        data = extract_fields_hdfc(text)
    elif issuer == "CITI":
        data = extract_fields_citi(text)
    elif issuer == "AXIS":
        data = extract_fields_axis(text)
    else:
        data = extract_fields_generic(text)
    data["issuer"] = issuer
    return data

# ============================================================
# MAIN PARSER
# ============================================================
def parse_credit_card_statement(pdf_path, save_debug_text=False):
    text = ocr_pdf_to_text(pdf_path)
    if not text:
        logging.error(f"OCR failed for {pdf_path}")
        return {"issuer": "UNKNOWN", "used_ocr": True, "source_file": os.path.basename(pdf_path)}
    
    if save_debug_text:
        debug_txt = os.path.join(DEBUG_DIR,
                               os.path.basename(pdf_path).replace(".pdf", "_ocr.txt"))
        with open(debug_txt, "w", encoding="utf-8") as f:
            f.write(text)
            logging.info(f"Saved debug text to: {debug_txt}")
    
    fields = extract_data_points(text)
    fields["used_ocr"] = True
    fields["source_file"] = os.path.basename(pdf_path)
    return fields

# ============================================================
# MAIN EXECUTION
# ============================================================
if __name__ == "__main__":
    if not os.path.exists(STATEMENTS_DIR):
        logging.error(f"Statements directory not found: {STATEMENTS_DIR}")
        exit(1)

    pdf_files = [f for f in os.listdir(STATEMENTS_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        logging.error(f"No PDF files found in: {STATEMENTS_DIR}")
        exit(1)

    results = []
    for pdf_file in pdf_files:
        pdf_path = os.path.join(STATEMENTS_DIR, pdf_file)
        logging.info(f"Processing: {pdf_path}")
        res = parse_credit_card_statement(pdf_path, save_debug_text=True)
        results.append(res)

    output_json = os.path.join(OUTPUT_DIR, "parsed_statements.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logging.info(f"✅ Parsing complete. Results saved to: {output_json}")

