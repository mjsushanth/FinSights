from generation.llm_client import create_llm_client

print("Testing AWS Bedrock Connection...")
print("=" * 70)

try:
    # Create client
    llm_client = create_llm_client()
    
    # Test connection
    if llm_client.test_connection():
        print("\n✅ Bedrock Connection Test PASSED")
    else:
        print("\n❌ Bedrock Connection Test FAILED")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nMake sure:")
    print("1. AWS credentials are configured")
    print("2. You have access to Bedrock")
    print("3. Claude model is enabled in your region")