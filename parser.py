import re
import PyPDF2 #type: ignore
import pandas as pd
import sys
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# --- Helpers ---------------------------------------------------------------

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file (best-effort)."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The file '{pdf_path}' was not found.")
    pages = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            page_text = page_text.replace("ﬁ", "fi").replace("ﬀ", "ff")
            page_text = re.sub(r'\r\n?', '\n', page_text)
            page_text = re.sub(r'\n\s*\n+', '\n', page_text).strip()
            pages.append(page_text)
    return "\n\n===PAGE_BREAK===\n\n".join(pages)


def try_date_parse(s):
    """Try several common date formats and return ISO format YYYY-MM-DD if possible."""
    if not s:
        return None
    s = str(s).strip()
    s = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', s)
    s = s.replace(',', '').strip()
    candidates = [
        "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y",
        "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%Y-%m-%d",
        "%b %d %Y", "%b %d, %Y", "%d %b %y"
    ]
    for fmt in candidates:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    m = re.search(r'(\d{1,2})[^\d]?(\d{1,2})[^\d]?(\d{2,4})', s)
    if m:
        d, mth, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        try:
            return datetime(int(y), int(mth), int(d)).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def normalize_amount(s):
    """Return cleaned numeric string and float value when possible."""
    if not s:
        return (None, None)
    s = str(s).strip()
    if s in ('.', '-', ''):
        return (None, None)
    s = re.sub(r'\S+@\S+\.\S+', '', s)  # drop emails
    s = re.sub(r'[^\d\-\.,()]+', '', s)
    negative = False
    if '(' in s and ')' in s:
        negative = True
        s = s.replace('(', '').replace(')', '')
    s = s.replace(',', '').replace(' ', '')
    if s.count('.') > 1:
        parts = s.split('.')
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    if s == '.':
        return (None, None)
    try:
        v = float(s)
        if negative:
            v = -abs(v)
        return (f"{v:.2f}", v)
    except Exception:
        return (None, None)


def compile_patterns(list_of):
    return [re.compile(p, re.IGNORECASE | re.DOTALL) if isinstance(p, str) else p for p in list_of]


def search_patterns(text, regex_list):
    """Try multiple regex patterns and return best capture (group preferred)."""
    for pat in regex_list:
        m = pat.search(text)
        if m:
            if m.lastindex:
                # prefer last non-empty capture
                for i in range(m.lastindex, 0, -1):
                    g = m.group(i)
                    if g and g.strip():
                        return g.strip()
            val = m.group(0).strip()
            return val
    return None


def find_line_with_keyword(text, keywords, window=1):
    parts = re.split(r'\n|===PAGE_BREAK===', text)
    for i, part in enumerate(parts):
        s = part.strip()
        for kw in keywords:
            if kw.lower() in s.lower():
                start = max(0, i - window)
                end = min(len(parts), i + window + 1)
                return "\n".join(p.strip() for p in parts[start:end] if p.strip())
    return None


def find_uppercase_name(text):
    """Try find NAME in uppercase near top of first page (common on statements)."""
    first_page = text.split("===PAGE_BREAK===")[0]
    lines = [l.strip() for l in first_page.splitlines() if l.strip()]
    # prefer lines that are ALL CAPS and contain 2..4 words
    for l in lines[:40]:
        if re.match(r'^[A-Z][A-Z\s\-\']{3,}$', l) and len(l.split()) <= 4 and len(l.split()) >= 2:
            # avoid pure labels
            if not re.search(r'(statement|account|card|due|date|page|summary|balance)', l, re.IGNORECASE):
                return l.title()
    return None


# --- Issuer detection -----------------------------------------------------

def identify_issuer(text):
    t = text.lower()
    if ("hdfc" in t and "card" in t) or "hdfc bank" in t:
        return "HDFC"
    if ("icici" in t and "card" in t) or "icici bank" in t:
        return "ICICI"
    if "idfc" in t or "idfc first" in t:
        return "IDFC"
    if "citi" in t or "citibank" in t or "citicorp" in t:
        return "CITI"
    if "state bank of india" in t or "sbi card" in t or re.search(r'\bsbi\b', t):
        return "SBI"
    return None


# --- Patterns for each issuer --------------------------------------------

def get_patterns():
    p = {
        'HDFC': {
            'cardholder_name': [
                r"Cardholder\s*Name[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Name\s*:\s*([A-Z][A-Za-z\s]{2,80})",
                r"Dear\s+(?:Mr\.|Ms\.|Mrs\.)\s*([A-Z][A-Za-z\s]{2,80})"
            ],
            'card_last_4': [
                r"(?:Card(?:\s*No|number|ending)|ending\s+in)\s*[:\s]*[Xx\-\s]*.*?(\d{4})",
                r"(\d{4})\b(?=\s*Card)"
            ],
            'statement_date': [
                r"Statement Date[:\s]*([\d/\\\-\s]{6,30})",
                r"Statement Period[:\s]*([\d/\\\-\stoand]{6,60})"
            ],
            'payment_due_date': [
                r"Payment Due Date[:\s]*([\d/\\\-\s]{6,30})",
                r"Due Date[:\s]*([\d/\\\-\s]{6,30})"
            ],
            'total_balance': [
                r"Total Due[s]*[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)",
                r"Amount Due[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)"
            ]
        },
        'ICICI': {
            'cardholder_name': [
                r"Customer Name[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Dear\s+(?:Mr\.|Ms\.|Mrs\.)\s*([A-Z][A-Za-z\s]{2,80})",
                r"Cardmember[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Statement for[:\s]*([A-Z][A-Za-z\s,\.]{2,80})"
            ],
            'card_last_4': [
                r"(?:Card Account No|Card Number|Ending)\s*[:\s]*[Xx\-\s]*.*?(\d{4})",
                r"XXXX\s*(\d{4})"
            ],
            'statement_date': [
                r"Statement Date[:\s]*([\d/\\\-\s]{6,30})",
                r"Statement Period[:\s]*([\d/\\\-\stoand]{6,60})"
            ],
            'payment_due_date': [
                r"(?:Due Date|Payment Due Date|Payment Due)[:\s]*([\d/\\\-\s]{6,30})"
            ],
            'total_balance': [
                r"Total Amount Due[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)",
                r"Amount Due[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)"
            ]
        },
        'IDFC': {
            'cardholder_name': [
                r"Cardholder Name[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Dear\s+(?:Mr\.|Ms\.|Mrs\.)\s*([A-Z][A-Za-z\s]{2,80})"
            ],
            'card_last_4': [
                r"(?:Card Number|Card No|Ending)\s*[:\s]*[Xx\-\s]*.*?(\d{4})",
                r"XXXX\s*(\d{4})"
            ],
            'statement_date': [
                r"Statement Date[:\s]*([\d/\\\-\s]{6,30})",
                r"Statement Period[:\s]*([\d/\\\-\stoand]{6,60})"
            ],
            'payment_due_date': [
                r"(?:Payment Due Date|Due Date)[:\s]*([\d/\\\-\s]{6,30})"
            ],
            'total_balance': [
                r"Total Amount Due[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)",
                r"Amount Due[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)"
            ]
        },
        'CITI': {
            'cardholder_name': [
                r"Cardmember(?: Name)?[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Dear\s+(?:Mr\.|Ms\.|Mrs\.)\s*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Statement for[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Account Holder[:\s]*([A-Z][A-Za-z\s,\.]{2,80})"
            ],
            'card_last_4': [
                r"(?:Card Number|Card No|ending in|ending with)\s*[:\s]*[Xx\-\s]*.*?(\d{4})",
                r"XXXX\s*(\d{4})"
            ],
            'statement_date': [
                r"Statement Date[:\s]*([\d/\\\-\s]{6,30})",
                r"Statement Period[:\s]*([\d/\\\-\stoand]{6,60})"
            ],
            'payment_due_date': [
                r"(?:Payment Due Date|Due Date|Amount Due Date)[:\s]*([\d/\\\-\s]{6,30})",
                r"(?:Pay By)[:\s]*([\d/\\\-\s]{6,30})"
            ],
            'total_balance': [
                r"(?:Total Amount Due|Amount Due|Total Due|Outstanding Balance)[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)",
                r"Balance Due[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)"
            ]
        },
        'SBI': {
            'cardholder_name': [
                r"Customer Name[:\s]*([A-Z][A-Za-z\s,\.]{2,80})",
                r"Cardholder[:\s]*([A-Z][A-Za-z\s]{2,80})"
            ],
            'card_last_4': [
                r"(?:Card Number|Card No|ending)\s*[:\s]*[Xx\-\s]*.*?(\d{4})",
                r"XXXX\s*(\d{4})"
            ],
            'statement_date': [
                r"Statement Date[:\s]*([\d/\\\-\s]{6,30})",
                r"Statement Period[:\s]*([\d/\\\-\stoand]{6,60})"
            ],
            'payment_due_date': [
                r"(?:Payment Due Date|Due Date)[:\s]*([\d/\\\-\s]{6,30})"
            ],
            'total_balance': [
                r"(?:Total Due|Total Amount Due|Outstanding Balance)[:\s]*(?:₹|\$)?\s*([-\d,\.()]+)"
            ]
        }
    }
    compiled = {}
    for issuer, fields in p.items():
        compiled[issuer] = {}
        for field, pats in fields.items():
            compiled[issuer][field] = compile_patterns(pats)
    return compiled


# --- Main parsing logic ---------------------------------------------------

def clean_name(raw):
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r'\bEmail\b.*', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'\S+@\S+\.\S+', '', s).strip()
    s = re.sub(r'[\s,;:]+$', '', re.sub(r'\s+', ' ', s)).strip()
    return s if s else None


def find_amount_near_keyword(text, keywords):
    frag = find_line_with_keyword(text, keywords, window=1)
    if frag:
        # find amounts in fragment
        amts = re.findall(r'([-\d\.,()]{2,}\d)', frag)
        for a in amts:
            c, v = normalize_amount(a)
            if v is not None:
                return c, v
    return (None, None)


def find_likely_total(text):
    # prefer labeled totals first
    labels = ['total amount due','amount due','total due','outstanding balance','balance due','amount payable']
    c, v = find_amount_near_keyword(text, labels)
    if v is not None:
        return c, v
    # fallback: collect monetary values on first page and choose the largest positive value
    first_page = text.split("===PAGE_BREAK===")[0]
    candidates = re.findall(r'(?:₹|\$)?\s*([-\d\.,()]{2,}\d)', first_page)
    vals = []
    for raw in candidates:
        c, v = normalize_amount(raw)
        if v is not None and v >= 0:
            vals.append((c, v))
    if vals:
        # choose largest numeric value
        chosen = max(vals, key=lambda x: x[1])
        return chosen
    return (None, None)


def is_reasonable_name(s):
    if not s:
        return False
    s = s.strip()
    if len(s) < 4:
        return False
    if len(s.split()) < 1:
        return False
    # must contain letters
    return bool(re.search(r'[A-Za-z]', s))


def parse_statement(text):
    issuer = identify_issuer(text)
    if not issuer:
        return {"error": "Could not determine the card issuer."}
    patterns = get_patterns()
    issuer_patterns = patterns.get(issuer, {})

    extracted = {"issuer": issuer}
    fields = ['cardholder_name', 'card_last_4', 'statement_date', 'payment_due_date', 'total_balance']
    for field in fields:
        val = None
        pats = issuer_patterns.get(field, [])
        if pats:
            val = search_patterns(text, pats)
        # fallbacks per field
        if not val:
            if field == 'cardholder_name':
                # try uppercase name on first page
                val = find_uppercase_name(text)
                if not val:
                    frag = find_line_with_keyword(text, ['dear', 'cardmember', 'customer name', 'statement for', 'account holder'])
                    if frag:
                        val = search_patterns(frag, pats) if pats else None
                if not val:
                    # look for a labeled pattern like "Statement for <NAME>"
                    m = re.search(r'Statement for[:\s]*([A-Za-z][A-Za-z\s\.\-]{2,80})', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
            elif field == 'card_last_4':
                frag = find_line_with_keyword(text, ['card', 'ending', 'card number', 'xxxx'])
                if frag:
                    val = search_patterns(frag, pats) if pats else None
                if not val:
                    m = re.search(r'(?:x{2,}|\bxxxx\b|ending\s+(?:in|with)?).{0,60}?(\d{4})', text, re.IGNORECASE | re.DOTALL)
                    if m:
                        val = m.group(1)
            elif field in ('statement_date', 'payment_due_date'):
                frag = find_line_with_keyword(text, ['statement date', 'statement period', 'due date', 'payment due', 'pay by'])
                if frag:
                    val = search_patterns(frag, pats) if pats else None
                if not val:
                    # try any date-like token
                    m = re.search(r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})', text)
                    if m:
                        val = m.group(1)
            elif field == 'total_balance':
                # try labeled totals first
                c, v = find_likely_total(text)
                if v is not None:
                    val = c
        extracted[field] = val

    # normalize and validate
    # cardholder
    name = extracted.get('cardholder_name')
    if is_reasonable_name(name):
        extracted['cardholder_name'] = clean_name(name)
    else:
        extracted['cardholder_name'] = None

    # card last 4
    last4 = extracted.get('card_last_4')
    if last4:
        m = re.search(r'(\d{4})', str(last4))
        extracted['card_last_4'] = m.group(1) if m else None
    else:
        extracted['card_last_4'] = None

    # statement date
    sd = extracted.get('statement_date')
    extracted['statement_date_normalized'] = try_date_parse(sd) or None

    # payment due date
    pd = extracted.get('payment_due_date')
    extracted['payment_due_date_normalized'] = try_date_parse(pd) or None

    # total balance
    amt_raw = extracted.get('total_balance')
    if not amt_raw:
        # try one more time using labeled search
        c, v = find_likely_total(text)
        extracted['total_balance_clean'], extracted['total_balance_value'] = c, v
    else:
        c, v = normalize_amount(amt_raw)
        extracted['total_balance_clean'], extracted['total_balance_value'] = c, v

    return extracted


# --- CLI / Runner ---------------------------------------------------------

def main():
    folder = "statements"
    if len(sys.argv) > 1:
        folder = sys.argv[1]

    if not os.path.isdir(folder):
        logging.error("Statements folder '%s' does not exist.", folder)
        sys.exit(1)

    pdf_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith('.pdf')]
    if not pdf_files:
        logging.info("No PDF files found in '%s'.", folder)
        return

    all_data = []
    for path in pdf_files:
        logging.info("Processing %s", path)
        try:
            text = extract_text_from_pdf(path)
            parsed = parse_statement(text)
            parsed['file_name'] = os.path.basename(path)
            all_data.append(parsed)
            if "error" in parsed:
                logging.warning("File %s: %s", path, parsed["error"])
            else:
                print(f"\nFile: {parsed['file_name']}")
                print(f"Issuer: {parsed.get('issuer')}")
                print(f"Cardholder: {parsed.get('cardholder_name') or 'Not found'}")
                print(f"Last4: {parsed.get('card_last_4') or 'Not found'}")
                print(f"Statement Date: {parsed.get('statement_date_normalized') or 'Not found'}")
                print(f"Due Date: {parsed.get('payment_due_date_normalized') or 'Not found'}")
                print(f"Total Balance: {parsed.get('total_balance_clean') or 'Not found'}")
        except FileNotFoundError as e:
            logging.error(e)
        except Exception as e:
            logging.exception("Failed to parse %s: %s", path, e)

    if all_data:
        df = pd.DataFrame(all_data)
        cols = [
            'file_name', 'issuer', 'cardholder_name', 'card_last_4',
            'statement_date_normalized', 'payment_due_date_normalized',
            'total_balance_clean', 'total_balance_value'
        ]
        cols = [c for c in cols if c in df.columns]
        print("\nSummary:")
        print(df[cols].fillna("Not Found").to_string(index=False))


if __name__ == "__main__":
    main()

