# Start Flask app in background
Start-Process -NoNewWindow python app.py

# Wait a bit
Start-Sleep -Seconds 5

# Start ngrok
.\ngrok.exe http 5000