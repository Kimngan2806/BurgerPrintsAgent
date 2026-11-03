import asyncio
import os
import sys

# Đảm bảo import được các module từ thư mục backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from agent.vertex_agent import VertexAgent

async def test_vertex_api():
    print("🚀 Bắt đầu test kết nối Vertex AI API...")
    try:
        # Khởi tạo agent (Sẽ tự động nạp cấu hình từ .env và load file JSON credentials)
        agent = VertexAgent()
        
        print(f"✅ Khởi tạo Agent thành công. Đang dùng model: {agent.model_name}")
        
        # Gửi một câu lệnh test nhẹ
        test_message = "Xin chào, bạn có thể nghe tôi nói không? Trả lời ngắn gọn 1 câu."
        print(f"📩 Đang gửi tin nhắn: '{test_message}'")
        
        # Chạy hàm send_message (tạm thời không truyền history và fake session)
        response_text = ""
        async for chunk in agent.send_message(test_message, session_id="test_vertex_001"):
            # Lọc bỏ các dấu hiệu đặc biệt nếu có
            if chunk and not chunk.startswith("@@TOOL_"):
                response_text += chunk
                
        print(f"🤖 Vertex AI phản hồi: {response_text}")
        print("🎉 Test thành công!")
        
    except Exception as e:
        print(f"❌ Test thất bại! Lỗi: {e}")

if __name__ == "__main__":
    asyncio.run(test_vertex_api())
