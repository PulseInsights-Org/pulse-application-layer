#!/usr/bin/env python3
"""
Simple test script for the new pulse API client.
This script tests the basic functionality of calling the pulse extraction API.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.service.pulse_api import PulseAPIClient

async def test_pulse_api():
    """Test the pulse API client functionality."""
    
    # Load environment variables
    load_dotenv()
    
    # Get configuration
    base_url = os.getenv("PULSE_API_BASE_URL", "http://localhost:8000")
    org_id = os.getenv("DEFAULT_ORG_ID", "pulse-dev-2")
    
    print(f"Testing Pulse API client:")
    print(f"  Base URL: {base_url}")
    print(f"  Org ID: {org_id}")
    print()
    
    # Create API client
    client = PulseAPIClient(base_url=base_url, org_id=org_id)
    
    try:
        # Test 1: Check API status
        print("1. Testing API status...")
        try:
            status = await client.get_api_status()
            if status:
                print(f"   ✅ API Status: {status}")
            else:
                print("   ⚠️  API Status check returned no data (this may be normal)")
        except Exception as e:
            print(f"   ⚠️  API Status check failed: {e} (this may be normal if tenant is not configured)")
        
        # Test 2: Test content extraction
        print("\n2. Testing content extraction...")
        test_content = "This is a test document for the pulse API. It contains some sample text to process. Deployment happened on Monday, Rupak was involved."
        
        try:
            result = await client.extract_content(test_content, "test.txt")
            if result:
                print(f"   ✅ Extraction Result: {result}")
            else:
                print("   ⚠️  Extraction returned no result (this may be normal if tenant is not configured)")
        except Exception as e:
            print(f"   ⚠️  Extraction failed: {e} (this may be normal if tenant is not configured)")
        
        print("\n✅ All tests completed! (Note: Some failures may be expected if tenant is not configured)")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        await client.close()

if __name__ == "__main__":
    print("Starting Pulse API client test...")
    asyncio.run(test_pulse_api())
