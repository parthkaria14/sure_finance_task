import re
import PyPDF2
import pandas as pd
import sys
import os

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Error: The file '{pdf_path}' was not found.")
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            # Extract text and replace common ligature issues and clean up spacing
            page_text = page.extract_text() or ""
            # Consolidate multiple newlines and surrounding spaces into a single newline
            clean_text = re.sub(r'\s*\n\s*', '\n', page_text) 
            text += clean_text.replace('ﬁ', 'fi').replace('ﬀ', 'ff')
    return text

def identify_issuer(text):
    """Identifies the credit card issuer from the text."""
    if re.search(r'HDFC\s*BANK', text, re.IGNORECASE):
        return "HDFC"
    if re.search(r'ICICI\s*Bank', text, re.IGNORECASE):
        return "ICICI"
    if re.search(r'IDFC\s*FIRST\s*Bank', text, re.IGNORECASE):
        return "IDFC"
    if re.search(r'c[íi]ti', text, re.IGNORECASE) and "citibank.com.ph" in text:
        return "CITI"
    return None

def parse_statement(text):
    """Parses the extracted text to find key data points based on the issuer."""
    
    issuer = identify_issuer(text)
    if not issuer:
        return {"error": "Could not determine the card issuer."}

    # --- Heavily Revised Regex Patterns for High Accuracy ---
    # These patterns are tailored to the specific and often messy layout of each PDF.
    patterns = {
        'HDFC': {
            'cardholder_name': [re.compile(r"Name\s*:\s*([A-Z\s]+?)\s*Email", re.IGNORECASE)],
            'card_last_4': [re.compile(r"Card No:\s*[\dX\s]+(\d{4})")],
            'total_balance': [re.compile(r"Total Dues\s*\n\s*([\d,]+\.\d{2})")],
            'payment_due_date': [re.compile(r"Payment Due Date\s+Total Dues.*?\n\s*(\d{2}/\d{2}/\d{4})")],
            'statement_date': [re.compile(r"Statement Date:\s*(\d{2}/\d{2}/\d{4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due\s*₹\s*([\d,]+\.\d{2})")]
        
        },
        'ICICI': {
            'cardholder_name': [re.compile(r"Customer Name\s*\n(Mr\.?\s*[A-Z\s]+?)\n", re.IGNORECASE)],
            'card_last_4': [re.compile(r"Card Account No\s*[\d\sX]+(\d{4})")],
            'total_balance': [re.compile(r"Your Total Amount Due.*?₹\s*([\d,]+\.\d{2})", re.DOTALL)],
            'payment_due_date': [re.compile(r"Due Date:\s*(\d{2}/\d{2}/\d{4})")],
            'statement_date': [re.compile(r"Statement Date\s+(\d{2}/\d{2}/\d{4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due.*?₹\s*([\d,]+\.\d{2})", re.DOTALL)]
        },
        'IDFC': {
            'cardholder_name': [re.compile(r"\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\n([A-Za-z\s]+?)\nHouse No", re.DOTALL)],
            'card_last_4': [re.compile(r"Card Number:\s*XXXX (\d{4})")],
            'total_balance': [re.compile(r"Total Amount Due\s*\n([\d,]+\.\d{2})\s*\nBalance")],
            'payment_due_date': [re.compile(r"Payment Due Date\s*\n(\d{2}/\d{2}/\d{4})\s*\nLate payment fee")],
            'statement_date': [re.compile(r"Statement Date\n(\d{2}/\d{2}/\d{4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due\s*\n([\d,]+\.\d{2})\s*\nPayment Due Date")]
        },
        'CITI': {
            'cardholder_name': [re.compile(r'C\*\s*\n\s*([A-Z\s]+?)\n\s*#')],
            'card_last_4': [re.compile(r'Card Number\s*:\s*[\d\-]+-(\d{4})')],
            'total_balance': [re.compile(r'Total Amount Due \(P\)\s*:\s*([\d,]+\.\d{2})')],
            'payment_due_date': [re.compile(r'Payment Due Date\s*:\s*(\d{2}/\d{2}/\d{2,4})')],
            'statement_date': [re.compile(r'Statement Date\s*:\s*(\d{2}/\d{2}/\d{2,4})')],
            'minimum_amount_due': [re.compile(r'Minimum Amount Due \(P\)\s*:\s*([\d,]+\.\d{2})')]
        }
    }

    extracted_data = {'issuer': issuer}
    issuer_patterns = patterns.get(issuer, {})
    
    for key, regex_list in issuer_patterns.items():
        for pattern in regex_list:
            match = pattern.search(text)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                # Clean up the extracted value by stripping whitespace and removing newlines
                value = re.sub(r'\s+', ' ', value).strip()
                extracted_data[key] = value
                break
        if key not in extracted_data:
             extracted_data[key] = None # If no pattern matched

    return extracted_data

def main():
    """Main function to run the PDF parser on a list of files."""
    
    statement_folder = 'statements'
    pdf_files = [
        'citi_statement.pdf',
        'hdfc_statement.pdf',
        'icici_statement.pdf',
        'idfc_statement.pdf'
    ]
    
    pdf_paths = [os.path.join(statement_folder, f) for f in pdf_files]

    all_data = []

    for pdf_path in pdf_paths:
        print(f"--- Processing: {pdf_path} ---")
        try:
            statement_text = extract_text_from_pdf(pdf_path)
            parsed_data = parse_statement(statement_text)
            parsed_data['file_name'] = pdf_path 
            all_data.append(parsed_data)
            
            if "error" in parsed_data:
                print(f"Error: {parsed_data['error']}\n")
            else:
                for key, value in parsed_data.items():
                    print(f"{key.replace('_', ' ').title():>20}: {value}")
                print("-" * 35 + "\n")

        except FileNotFoundError as e:
            print(e)
            print("-" * 35 + "\n")
        except Exception as e:
            print(f"An unexpected error occurred while processing {pdf_path}: {e}")
            print("-" * 35 + "\n")
            
    if all_data:
        print("\n--- Summary of All Parsed Statements ---")
        df = pd.DataFrame(all_data)
        
        cols = ['file_name', 'issuer', 'cardholder_name', 'card_last_4', 'statement_date', 'payment_due_date', 'total_balance', 'minimum_amount_due']
        df_cols = [c for c in cols if c in df.columns]
        
        # Format the dataframe to fill None values with 'Not Found' for clarity
        print(df[df_cols].fillna('Not Found').to_string(index=False))
        print("----------------------------------------")


if __name__ == '__main__':
    main()

