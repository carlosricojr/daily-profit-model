import os
import csv
import io
import requests
from datetime import datetime
from typing import List, Set
import psycopg2
from psycopg2.extras import execute_batch


def download_csv(api_key: str) -> str:
    """Download CSV from FTF Hub API."""
    url = "https://tfthubapiprod.fpfxtech.io/csv/customer"
    headers = {"fpfx-api-key": api_key}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    return response.text


def parse_csv(csv_content: str) -> List[dict]:
    """Parse CSV content and return list of records."""
    csv_reader = csv.DictReader(io.StringIO(csv_content))
    return list(csv_reader)


def filter_by_email(records: List[dict], filtered_emails_and_domains: Set[str]) -> List[str]:
    """Filter records by email and return customer numbers."""
    filtered_customer_numbers = []
    
    for record in records:
        email = record.get('email', '').lower()
        if not email:
            continue
            
        # Check if email matches exactly
        if email in filtered_emails_and_domains:
            filtered_customer_numbers.append(record['customerNumber'])
            continue
            
        # Check if domain matches
        if '@' in email:
            domain = email.split('@')[1]
            if domain in filtered_emails_and_domains:
                filtered_customer_numbers.append(record['customerNumber'])
    
    return filtered_customer_numbers


def insert_to_database(customer_numbers: List[str], reason: str = "test profile"):
    """Insert customer numbers into excluded_traders table."""
    # Get database connection from environment
    db_url = os.environ.get('DB_CONNECTION_STRING_SESSION_POOLER')
    if not db_url:
        raise ValueError("DB_CONNECTION_STRING_SESSION_POOLER environment variable not set")
    
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    try:
        # Prepare data for insertion
        now = datetime.utcnow()
        data = [(cn, reason, now) for cn in customer_numbers]
        
        # Insert with ON CONFLICT DO NOTHING to handle duplicates
        insert_query = """
            INSERT INTO prop_trading_model.excluded_traders (trader_id, reason, inserted_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (trader_id) DO NOTHING
        """
        
        execute_batch(cur, insert_query, data)
        conn.commit()
        
        # Get count of actual insertions
        cur.execute("""
            SELECT COUNT(*) FROM prop_trading_model.excluded_traders 
            WHERE trader_id = ANY(%s)
        """, (customer_numbers,))
        
        total_count = cur.fetchone()[0]
        
        print(f"Successfully processed {len(customer_numbers)} customer numbers")
        print(f"Total records in database for these traders: {total_count}")
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def main():
    # Configuration
    api_key = "*****"
    
    # Define the list of emails and domains to filter
    # You can modify this list as needed
    filtered_emails_and_domains = {
        'test.com',
        'test.io',
        'test',
        'eastontech.net',
        'thefundedtraderprogram.com',
        'arizet.com',
        'fpfxtech.io',
        'fpfxtech.com',
        'napollo.net',
        'napollo.online',
        'lennilsfx@yahoo.com',
        'test@test.com',
        'support@cryptoorange.com',
        'amantestemail2@yahoo.com',
        'amantestemail1@yahoo.com',
        'shervin.easton2@gmail.com',
        'shervin.easton@gmail.com'
    }
    
    # Download CSV
    print("Downloading CSV...")
    csv_content = download_csv(api_key)
    
    # Parse CSV
    print("Parsing CSV...")
    records = parse_csv(csv_content)
    print(f"Total records in CSV: {len(records)}")
    
    # Filter by email
    print("Filtering by email...")
    filtered_customer_numbers = filter_by_email(records, filtered_emails_and_domains)
    print(f"Filtered customer numbers: {len(filtered_customer_numbers)}")
    
    if not filtered_customer_numbers:
        print("No matching records found")
        return
    
    # Insert to database
    print("Inserting to database...")
    insert_to_database(filtered_customer_numbers)
    
    print("Done!")


if __name__ == "__main__":
    main()