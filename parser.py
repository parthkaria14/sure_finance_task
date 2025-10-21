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
            # Extract text and replace common ligature issues
            page_text = page.extract_text() or ""
            text += page_text.replace('ﬁ', 'fi').replace('ﬀ', 'ff')
    return text

def identify_issuer(text):
    """Identifies the credit card issuer from the text."""
    # Use more robust regex to identify issuer, ignoring case and spacing variations
    if re.search(r'HDFC\s*BANK', text, re.IGNORECASE):
        return "HDFC"
    if re.search(r'ICICI\s*Bank', text, re.IGNORECASE):
        return "ICICI"
    if re.search(r'IDFC\s*FIRST\s*Bank', text, re.IGNORECASE):
        return "IDFC"
    if re.search(r'c[íi]ti', text, re.IGNORECASE):
        return "CITI"
    return None

def parse_statement(text):
    """Parses the extracted text to find key data points based on the issuer."""
    
    issuer = identify_issuer(text)
    if not issuer:
        return {"error": "Could not determine the card issuer."}

    # --- Define more robust Regex Patterns for Each Issuer ---
    # These patterns are designed to be more flexible and handle multi-line values.
    patterns = {
        'HDFC': {
            'cardholder_name': [re.compile(r"Name\s*:\s*([A-Z\s]+?)\s*\n", re.IGNORECASE)],
            'card_last_4': [re.compile(r"Card No:\s*[\dX\s]+(\d{4})")],
            'total_balance': [re.compile(r"Total Dues\s*\n[^\n]+?\s([\d,]+\.\d{2})")],
            'payment_due_date': [re.compile(r"Payment Due Date\s*\n\s*(\d{2}/\d{2}/\d{4})")],
            'statement_date': [re.compile(r"Statement Date:\s*(\d{2}/\d{2}/\d{4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due\s*\n[^\n]+?\s([\d,]+\.\d{2})")]
        },
        'ICICI': {
            'cardholder_name': [re.compile(r"Customer Name\s*(Mr\.?\s*[A-Z\s]+?)\n", re.IGNORECASE)],
            'card_last_4': [re.compile(r"Card Account No\s+[\d\sX]+(\d{4})")],
            'total_balance': [re.compile(r"Your Total Amount Due\s*₹\s*([\d,]+\.\d{2})")],
            'payment_due_date': [re.compile(r"Due Date:\s*(\d{2}/\d{2}/\d{4})")],
            'statement_date': [re.compile(r"Statement Date\s+(\d{2}/\d{2}/\d{4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due\s*₹\s*([\d,]+\.\d{2})")]
        },
        'IDFC': {
            'cardholder_name': [re.compile(r"\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s*\n\s*([A-Za-z\s]+?)\n")],
            'card_last_4': [re.compile(r"Card Number:\s*XXXX\s*(\d{4})")],
            'total_balance': [re.compile(r"Total Amount Due\s*\n\s*([\d,]+\.\d{2})", re.DOTALL)],
            'payment_due_date': [re.compile(r"Payment Due Date\s*\n\s*(\d{2}/\d{2}/\d{4})", re.DOTALL)],
            'statement_date': [re.compile(r"Statement Date\s+(\d{2}/\d{2}/\d{4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due\s*\n\s*([\d,]+\.\d{2})", re.DOTALL)]
        },
        'CITI': {
            'cardholder_name': [re.compile(r"CLARABELLE MAE DELA ROSA", re.DOTALL)],
            'card_last_4': [re.compile(r"Card Number\s*,?\s*:\s*[\d-]+\s*-(\d{4})")],
            'total_balance': [re.compile(r"Total Amount Due\s*\(P\)\s*,?\s*:\s*([\d,]+\.\d{2})")],
            'payment_due_date': [re.compile(r"Payment Due Date\s*,?\s*:\s*(\d{2}/\d{2}/\d{2,4})")],
            'statement_date': [re.compile(r"Statement Date\s*,?\s*:\s*(\d{2}/\d{2}/\d{2,4})")],
            'minimum_amount_due': [re.compile(r"Minimum Amount Due\s*\(P\)\s*,?\s*:\s*([\d,]+\.\d{2})")]
        }
    }

    extracted_data = {'issuer': issuer}
    issuer_patterns = patterns.get(issuer, {})
    
    for key, regex_list in issuer_patterns.items():
        for pattern in regex_list:
            match = pattern.search(text)
            if match:
                # Group 1 is the captured value, Group 0 is the full match.
                # If a pattern has no capture group, match.group(0) is the result.
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
    
    # Assuming PDFs are in a 'statements' subdirectory as per the error log.
    # If they are in the same directory, just use the filename.
    statement_folder = 'statements'
    pdf_files = [
        'citi_statement.pdf',
        'hdfc_statement.pdf',
        'icici_statement.pdf',
        'idfc_statement.pdf'
    ]
    
    # Create the full path to the files
    pdf_paths = [os.path.join(statement_folder, f) for f in pdf_files]

    all_data = []

    for pdf_path in pdf_paths:
        print(f"--- Processing: {pdf_path} ---")
        try:
            # 1. Extract text from the PDF
            statement_text = extract_text_from_pdf(pdf_path)
            
            # 2. Parse the text to get structured data
            parsed_data = parse_statement(statement_text)
            parsed_data['file_name'] = pdf_path # Add filename for context
            all_data.append(parsed_data)
            
            # 3. Display individual extraction results
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
            
    # Display a summary dataframe of all processed files
    if all_data:
        print("\n--- Summary of All Parsed Statements ---")
        df = pd.DataFrame(all_data)
        
        # Reorder columns for better readability
        cols = ['file_name', 'issuer', 'cardholder_name', 'card_last_4', 'statement_date', 'payment_due_date', 'total_balance', 'minimum_amount_due']
        # Filter for columns that actually exist in the dataframe to avoid errors
        df_cols = [c for c in cols if c in df.columns]
        print(df[df_cols].to_string(index=False))
        print("----------------------------------------")


if __name__ == '__main__':
    main()

