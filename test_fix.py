import asyncio
import httpx
from app.service.pulse_api import PulseAPIClient

async def test_extraction():
    # Initialize the client for local testing
    client = PulseAPIClient(
        base_url="http://localhost:8000",  # Local pulse core
        org_id="pulse-dev-2"
    )
    
    try:
        # Test content
        test_content = "This is a test meeting about project updates. John discussed the timeline and Sarah presented budget numbers. The deadline is December 15th."
        
        print("🧪 Testing extraction API call...")
        print(f"   URL: {client.base_url}/api/v1/ingestion/")
        print(f"   Org ID: {client.org_id}")
        print(f"   Content length: {len(test_content)} characters")
        print()
        
        result = await client.extract_content(test_content, "test_meeting.txt")
        
        if result:
            print("✅ SUCCESS! API call worked:")
            print(f"   Message: {result.get('message', 'No message')}")
            print(f"   Filename: {result.get('filename', 'No filename')}")
            print(f"   File size: {result.get('file_size', 'No size')}")
            print(f"   Text length: {result.get('text_length', 'No length')}")
            print(f"   Chunk size: {result.get('chunk_size', 'No chunk size')}")
        else:
            print("❌ FAILED: API call returned None")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    print("🚀 Testing Pulse API Client Fix")
    print("=" * 50)
    asyncio.run(test_extraction())
