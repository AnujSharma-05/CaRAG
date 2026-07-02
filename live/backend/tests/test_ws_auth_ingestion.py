"""
Test: WebSocket Authentication and Ingestion Status events
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "live" / "backend"))
sys.path.insert(0, str(ROOT / "core_backend"))

def test_ws_manager_connects_and_adds_to_room():
    from src.ws_manager import ConnectionManager
    import asyncio
    from unittest.mock import AsyncMock
    
    manager = ConnectionManager()
    mock_ws = MagicMock()
    mock_ws.accept = AsyncMock()
    
    asyncio.run(manager.connect(user_id=1, group_id=10, websocket=mock_ws))
    
    assert 1 in manager.user_connections
    assert 10 in manager.group_rooms
    assert 1 in manager.group_rooms[10]
    print("PASS - ConnectionManager connects and adds user to room")

def test_ws_manager_disconnects_and_removes_from_room():
    from src.ws_manager import ConnectionManager
    import asyncio
    from unittest.mock import AsyncMock
    
    manager = ConnectionManager()
    mock_ws = MagicMock()
    mock_ws.accept = AsyncMock()
    
    asyncio.run(manager.connect(user_id=1, group_id=10, websocket=mock_ws))
    asyncio.run(manager.disconnect(user_id=1, group_id=10))
    
    assert 1 not in manager.user_connections
    assert 10 not in manager.group_rooms # room cleaned up
    print("PASS - ConnectionManager cleans up user and empty rooms")

if __name__ == "__main__":
    print("\n---- CaRAG Live API - WebSocket Tests ----\n")
    tests = [
        test_ws_manager_connects_and_adds_to_room,
        test_ws_manager_disconnects_and_removes_from_room,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL - {test.__name__}: {e}")

    print(f"\n---- Results: {passed}/{len(tests)} passed ----\n")
    sys.exit(0 if passed == len(tests) else 1)
