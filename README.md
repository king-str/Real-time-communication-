# CodeAlpha Task 4 - Real-Time Communication App

A beginner-friendly real-time communication and collaboration application.

## Technologies

- Python
- Flask
- Flask-SocketIO
- SQLite
- HTML
- CSS
- JavaScript
- WebRTC
- Socket.IO

## Features

- User registration
- User login/logout
- Create meeting room
- Join meeting using room code
- Real-time multi-user signaling
- Camera and microphone
- Video calling with WebRTC
- Screen sharing
- Real-time text chat
- File sharing
- Collaborative whiteboard
- Meeting participant list
- SQLite storage
- Password hashing

## Important WebRTC Note

WebRTC uses browser media permissions. The browser will ask for camera/microphone permission.

For a classroom/demo environment, run the Flask server locally and open the meeting in multiple browser tabs/windows. For users on different devices/networks, a production deployment normally also needs HTTPS and a TURN server.

## Run on Windows

Open the folder in VS Code.

### 1. Create virtual environment

```bash
python -m venv venv
```

### 2. Activate

```bash
venv\Scripts\activate
```

### 3. Install packages

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
python app.py
```

### 5. Open

```text
http://127.0.0.1:5000
```

## Demo

1. Register User 1.
2. Login.
3. Create a meeting room.
4. Copy the room code.
5. Open another browser tab.
6. Register/login as another user.
7. Join using the room code.
8. Allow camera and microphone.
9. Test video/audio.
10. Test chat.
11. Test screen sharing.
12. Test file upload.
13. Draw on the whiteboard.

## Database

The application automatically creates:

```text
communication.db
```

Tables:

- users
- rooms
- room_members
- messages

## Security

Passwords are stored using Werkzeug password hashing.

The application is an educational/internship project. Before production deployment, use a strong secret key, HTTPS, secure cookies, authentication hardening, upload validation, access controls, and a TURN server for WebRTC.
