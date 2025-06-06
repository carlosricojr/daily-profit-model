#!/usr/bin/env python3
"""Test what fields metrics endpoints actually return"""

import os
from src.utils.api_client import RiskAnalyticsAPIClient
import json

# Get API credentials
api_key = os.getenv('RISK_API_KEY') or os.getenv('API_KEY')
base_url = os.getenv('RISK_API_BASE_URL') or os.getenv('API_BASE_URL')

client = RiskAnalyticsAPIClient(api_key=api_key, base_url=base_url)

print("Testing daily metrics endpoint...")
try:
    # Get one page of daily metrics
    for page in client.get_metrics(metric_type="daily", dates=["20250601"]):
        if page and len(page) > 0:
            print(f"\nGot {len(page)} daily metrics")
            print("Sample daily metric fields:")
            sample = page[0]
            for key in sorted(sample.keys()):
                value = sample[key]
                print(f"  {key}: {type(value).__name__} = {value if not isinstance(value, (list, dict)) else '...'}")
        break
except Exception as e:
    print(f"Error: {e}")

print("\n" + "-"*80)

# Also test that we're getting the all-time response correctly
print("\nTesting alltime metrics with full response...")
try:
    response = client._make_request("v2/metrics/alltime", params={"limit": 1})
    data = client._extract_data_from_response(response)
    if data:
        print(f"Extracted {len(data)} records from response")
        print("Sample record (first 10 fields):")
        sample = data[0]
        for i, (key, value) in enumerate(sample.items()):
            if i >= 10:
                print(f"  ... and {len(sample) - 10} more fields")
                break
            print(f"  {key}: {type(value).__name__} = {value if not isinstance(value, (list, dict)) else '...'}")
except Exception as e:
    print(f"Error: {e}")

client.close()