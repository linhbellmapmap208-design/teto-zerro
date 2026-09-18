# AI Chat — Gemini & GLM (Python / Flask)

Bản Python của chatbot: Flask ở backend, giao diện kiểu Claude (sidebar lịch sử
chat, khung chat, ô nhập có nút đính kèm ảnh) viết bằng HTML/CSS/JS thuần,
nhúng ngay trong `api/index.py` — không cần bước build, không có thư mục con
dễ gõ nhầm tên như bản Next.js trước.

## Cấu trúc (chỉ có đúng những file này)

```
api/index.py       <- toàn bộ app: Flask routes + HTML/CSS/JS nhúng sẵn
requirements.txt   <- Flask, requests
vercel.json        <- điều hướng mọi request về api/index.py
.env.example
.gitignore
README.md
```

Không có thư mục `components`, `templates`, `static` nào cả — nên không còn
rủi ro gõ sai tên thư mục nữa.

## Chạy thử ở máy local

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=xxxxx      # Windows PowerShell: $env:GEMINI_API_KEY="xxxxx"
export GLM_API_KEY=xxxxx
python api/index.py
```

Muốn `python api/index.py` tự chạy server, thêm đoạn sau vào cuối file
`api/index.py` (không bắt buộc khi deploy Vercel, chỉ cần lúc chạy local):

```python
if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

Mở http://localhost:5000.

Lấy key ở đâu:
- Gemini: https://aistudio.google.com/apikey
- GLM (Zhipu AI / BigModel): https://open.bigmodel.cn (mục API Keys)

Không muốn đặt biến môi trường thì bấm nút ⚙ trong app, dán key vào — key chỉ
lưu trong trình duyệt của bạn (localStorage), gửi kèm mỗi request tới server
rồi server forward sang Gemini/GLM, không lưu lại phía server.

## Deploy lên Vercel

1. Đẩy toàn bộ thư mục này lên một repo GitHub.
2. Vào https://vercel.com/new → Import repo đó. Vercel sẽ tự nhận ra
   `api/index.py` là một Python Serverless Function nhờ có `requirements.txt`
   ở gốc repo — không cần chọn framework nào đặc biệt (chọn "Other" nếu nó hỏi).
3. Trong bước cấu hình, mở **Environment Variables**, thêm:
   - `GEMINI_API_KEY`
   - `GLM_API_KEY`
4. Bấm **Deploy**.

Hoặc dùng CLI:

```bash
npm i -g vercel
vercel
vercel env add GEMINI_API_KEY
vercel env add GLM_API_KEY
vercel --prod
```

## Vì sao trả lời không "chạy chữ" như bản cũ

Bản Next.js trước dùng streaming thật (server-sent events) từ Gemini/GLM.
Bản Python này gọi API theo kiểu chờ đủ câu trả lời rồi mới trả về (đơn giản,
ít lỗi khi chạy trên Vercel serverless hơn), sau đó front-end tự "đánh máy lại"
câu trả lời để vẫn có hiệu ứng chữ chạy dần giống Claude — nhìn thì giống hệt,
chỉ khác là chờ trọn câu trả lời xong mới bắt đầu hiện, không phải hiện tới
đâu AI nghĩ tới đó.

## Ghi chú / có thể mở rộng thêm

- Lịch sử chat lưu trên trình duyệt (`localStorage`), không có tài khoản.
  Muốn đồng bộ nhiều thiết bị thì cần thêm database.
- Ảnh gửi dưới dạng base64 trực tiếp trong request, phù hợp ảnh nhỏ/vừa.
- Model GLM có ảnh mặc định dùng `glm-4v-plus`.
