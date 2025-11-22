# frontend/test_chat_metrics.py (optional - just validates imports)
"""
Validate that chat and metrics modules can be imported.
"""

try:
    from frontend.chat import (
        render_chat_message,
        render_chat_history,
        handle_user_input,
        render_clear_button
    )
    print("✅ chat.py imports successful")
except Exception as e:
    print(f"❌ chat.py import failed: {e}")

try:
    from frontend.metrics import (
        display_query_metadata,
        display_sidebar_stats,
        display_error_message,
        format_cost,
        format_tokens
    )
    print("✅ metrics.py imports successful")
except Exception as e:
    print(f"❌ metrics.py import failed: {e}")

print("\n✅ All frontend modules ready!")


"""


deactivate
cd ModelPipeline
.\serving\frontend\venv_frontend\Scripts\Activate.ps1
cd serving
python -m frontend.test_chat_metrics
"""