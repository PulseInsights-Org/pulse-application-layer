"""
Test script for the extraction pipeline components.
Run this to verify everything is working before implementing the worker.
"""

import asyncio
import logging
from app.core.config import config
from app.service.gemini import GeminiModel
from app.core.extraction import Extraction

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_config():
    """Test configuration loading."""
    print("🔧 Testing configuration...")
    
    try:
        # Test basic config
        print(f"✅ Supabase URL: {config.supabase_url[:30]}...")
        print(f"✅ Supabase Key: {config.supabase_key[:10]}...")
        
        # Test tenant secrets loading (you'll need to provide a valid org_id)
        # Replace this with an actual org_id from your org_directory table
        test_org_id = "pulse-dev-2"  # Replace with a real org_id from your database
        
        print(f"🔄 Testing tenant secrets loading for org: {test_org_id}")
        print("   💡 Make sure this org_id exists in your org_directory table")
        
        success = config.load_tenant_secrets(test_org_id)
        
        if success:
            print(f"✅ Tenant secrets loaded successfully for tenant: {config.tenant_id}")
            
            # Test secrets access
            gemini_config = config.get_gemini_config()
            print(f"✅ Model Name: {gemini_config['model_name']}")
            print(f"✅ Model API Key: {gemini_config['api_key'][:10] if gemini_config['api_key'] else 'None'}...")
            
            # Show other available secrets
            print(f"✅ Pinecone Index: {config.get_secret('pinecone_index', 'Not set')}")
            print(f"✅ Neo4j URI: {config.get_secret('neo4j_uri', 'Not set')[:30] if config.get_secret('neo4j_uri') else 'Not set'}...")
            
            return True
        else:
            print("⚠️ Tenant secrets loading failed")
            print("   💡 Check that:")
            print("      - The org_id exists in org_directory table")
            print("      - There's a corresponding entry in tenant_secrets table")
            print("      - The org status is 'active'")
            return False
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

async def test_gemini():
    """Test Gemini model connection."""
    print("\n🤖 Testing Gemini model...")
    
    try:
        # Check if we have tenant secrets loaded
        if not config.has_tenant_secrets():
            print("❌ No tenant secrets loaded. Cannot test Gemini without database configuration.")
            print("   💡 Make sure to run test_config() first and it succeeds.")
            return False
        
        model = GeminiModel()
        print(f"✅ Gemini model initialized: {model.model_name}")
        
        # Test simple response
        response = model.get_response("Say 'Hello, World!' in one word.")
        print(f"✅ Test response: {response.text}")
        
        return True
        
    except Exception as e:
        print(f"❌ Gemini test failed: {e}")
        return False

async def test_extraction():
    """Test extraction engine."""
    print("\n🔍 Testing extraction engine...")
    
    try:
        # Check if we have tenant secrets loaded
        if not config.has_tenant_secrets():
            print("❌ No tenant secrets loaded. Cannot test extraction without database configuration.")
            print("   💡 Make sure to run test_config() first and it succeeds.")
            return False
        
        model = GeminiModel()
        extraction = Extraction(model)
        
        # Test with simple text
        test_text = """
        Meeting on January 15th, 2024.
        John Smith discussed the new feature deployment.
        The team agreed to launch by Friday.
        Sarah Johnson will handle the testing.
        """
        
        result = extraction.process_document(test_text)
        
        print(f"✅ Extraction completed:")
        print(f"   - Title: {result['title']}")
        print(f"   - Summary: {result['summary'][:100]}...")
        print(f"   - Entities: {len(result['entities'])}")
        print(f"   - Relationships: {len(result['relationships'])}")
        print(f"   - Topics: {result['topics']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Extraction test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🧪 Starting extraction pipeline tests...\n")
    
    tests = [
        ("Configuration", test_config),
        ("Gemini Model", test_gemini),
        ("Extraction Engine", test_extraction),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 Test Results:")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1
    
    if passed == len(results):
        print("🎉 All tests passed! The extraction pipeline is ready.")
    else:
        print("⚠️ Some tests failed. Check the errors above.")
        print("\n💡 Troubleshooting tips:")
        print("   1. Ensure your .env file has SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        print("   2. Check that the org_directory table exists and has your org_id")
        print("   3. Verify that tenant_secrets table has secrets for your tenant_id")
        print("   4. Make sure your Gemini API key is valid in the database")
        print("\n🔧 To set up test data:")
        print("   1. Run: python setup_database.py")
        print("   2. Update test_org_id in this file to match your data")
        print("   3. Update the sample data with your actual API keys in Supabase")
        print("   4. Run the tests again")

if __name__ == "__main__":
    asyncio.run(main())
