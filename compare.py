import cv2
import numpy as np
import face_recognition
import os
import serial
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import Course, AccessLog
import logging

# Arduino serial communication setup
arduino = serial.Serial(port='COM9', baudrate=9600, timeout=1)  

def send_to_arduino(command):
    """Send a command to the Arduino."""
    try:
        arduino.write(command.encode())
        time.sleep(0.1)  # Ensure proper communication
    except Exception as e:
        print(f"Error sending to Arduino: {e}")

# Setup logging
logging.basicConfig(filename='access_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

# Database setup
engine = create_engine('sqlite:///C:/Users/Administrator/app/instance/teachers.db')
Session = sessionmaker(bind=engine)
session = Session()

from sqlalchemy import and_

def log_access(name, status):
    """Log access events to both file and database, avoiding duplicates."""
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')

    # Avoid duplicate logs within a short time period
    existing_log = session.query(AccessLog).filter(
        and_(
            AccessLog.name == name,
            AccessLog.status == status,
            AccessLog.timestamp.between(
                (now - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S'),
                timestamp
            )
        )
    ).first()

    if existing_log:
        print(f"Duplicate log skipped for {name} with status '{status}'.")
        return  # Skip adding duplicate logs

    # Log to the database
    new_log = AccessLog(name=name, timestamp=timestamp, status=status)
    session.add(new_log)
    session.commit()

    # Log to the text file
    logging.info(f"{name} - {status}")


def is_access_allowed(name):
    """Check if the current time matches the course schedule for the detected face."""
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    # Query the course schedule
    course = session.query(Course).filter(
        Course.first_name.ilike(name.split('_')[0]),
        Course.last_name.ilike(name.split('_')[1]),
        Course.course_date == current_date,
        Course.start_time <= current_time,
        Course.end_time >= current_time
    ).first()

    return bool(course)

# Path for face images
path = 'uploads'
images = []
classNames = []

# Load face images from the upload directory
if not os.path.exists(path):
    print(f"Error: Directory '{path}' not found.")
    exit(1)

print("Loading images...")
for file_name in os.listdir(path):
    file_path = os.path.join(path, file_name)
    if os.path.isfile(file_path) and file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
        image = cv2.imread(file_path)
        if image is not None:
            images.append(image)
            classNames.append(os.path.splitext(file_name)[0])
        else:
            print(f"Warning: Could not load image {file_name}. Skipping.")
    else:
        print(f"Warning: {file_name} is not a supported image file. Skipping.")

if not images:
    print("Error: No valid images found in the directory.")
    exit(1)

print(f"Loaded class names: {classNames}")

# Encode faces
def findEncodings(images):
    encodeList = []
    for idx, img in enumerate(images):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        try:
            encode = face_recognition.face_encodings(img)[0]
            encodeList.append(encode)
        except IndexError:
            print(f"Warning: No face detected in image '{classNames[idx]}'. Skipping.")
    return encodeList

print("Encoding faces...")
encodeListKnown = findEncodings(images)
if not encodeListKnown:
    print("Error: No faces encoded from the images.")
    exit(1)
print("Encoding complete.")

# Start video capture
print("Starting video capture...")
cap = cv2.VideoCapture(0)

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture frame from camera.")
            break

        # Resize frame for faster processing
        frame_small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        frame_small_rgb = cv2.cvtColor(frame_small, cv2.COLOR_BGR2RGB)

        # Detect faces and encodings in the current frame
        face_locations = face_recognition.face_locations(frame_small_rgb)
        face_encodings = face_recognition.face_encodings(frame_small_rgb, face_locations)

        for face_encoding, face_location in zip(face_encodings, face_locations):
            matches = face_recognition.compare_faces(encodeListKnown, face_encoding)
            face_distances = face_recognition.face_distance(encodeListKnown, face_encoding)

            if matches:
                match_index = np.argmin(face_distances)
                if matches[match_index]:
                    name = classNames[match_index]
                    if is_access_allowed(name):
                        # Grant access
                        send_to_arduino('1')
                        log_access(name, 'Granted')
                        print(f"Access granted for {name}")
                    else:
                        # Deny access (time mismatch)
                        send_to_arduino('0')
                        log_access(name, 'Denied')
                        print(f"Access denied for {name} (Out of schedule)")

                    # Scale face location back to original frame size
                    y1, x2, y2, x1 = [coord * 4 for coord in face_location]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.rectangle(frame, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
                    cv2.putText(frame, name, (x1 + 6, y2 - 6), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)

        # Display the frame
        cv2.imshow('Face Recognition', frame)

        # Break loop on 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Exiting...")
            break
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("Resources released.")
