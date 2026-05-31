import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2
import face_recognition
import numpy as np
import serial
from dotenv import load_dotenv
from sqlalchemy import and_, create_engine
from sqlalchemy.orm import sessionmaker

from models import AccessLog, Course


GRANT_COMMAND = b"1"
DENY_COMMAND = b"0"
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@dataclass(frozen=True)
class WorkerConfig:
    database_url: str
    upload_folder: Path
    serial_port: str
    baudrate: int
    camera_index: int
    access_log_file: Optional[Path]


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


def load_config() -> WorkerConfig:
    load_dotenv()
    database_url = os.environ.get("RECOGNITION_DATABASE_URL") or _required_env(
        "DATABASE_URL",
    )
    upload_folder = Path(
        os.environ.get("RECOGNITION_UPLOAD_FOLDER")
        or os.environ.get("UPLOAD_FOLDER", "uploads"),
    ).resolve()
    access_log_file = os.environ.get("ACCESS_LOG_FILE")

    return WorkerConfig(
        database_url=database_url,
        upload_folder=upload_folder,
        serial_port=_required_env("ARDUINO_SERIAL_PORT"),
        baudrate=_env_int("ARDUINO_BAUDRATE", 9600),
        camera_index=_env_int("CAMERA_INDEX", 0),
        access_log_file=Path(access_log_file).resolve() if access_log_file else None,
    )


def configure_logging(config: WorkerConfig) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if config.access_log_file:
        config.access_log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(config.access_log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def create_session(database_url: str):
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def open_controller(config: WorkerConfig):
    try:
        controller = serial.Serial(
            port=config.serial_port,
            baudrate=config.baudrate,
            timeout=1,
            write_timeout=1,
        )
        logging.info("Connected to controller on %s", config.serial_port)
        return controller
    except serial.SerialException as exc:
        logging.error("Controller unavailable on %s: %s", config.serial_port, exc)
        return None


def send_to_controller(controller, command: bytes) -> bool:
    if controller is None:
        logging.error("Controller command blocked because no serial connection is open")
        return False

    try:
        controller.write(command)
        controller.flush()
        time.sleep(0.1)
        return True
    except serial.SerialException as exc:
        logging.error("Controller command failed: %s", exc)
        return False


def log_access(session, name: str, status: str) -> None:
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    existing_log = (
        session.query(AccessLog)
        .filter(
            and_(
                AccessLog.name == name,
                AccessLog.status == status,
                AccessLog.timestamp.between(
                    (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
                    timestamp,
                ),
            ),
        )
        .first()
    )
    if existing_log:
        logging.info("Duplicate access log skipped for %s with status %s", name, status)
        return

    session.add(AccessLog(name=name, timestamp=timestamp, status=status))
    session.commit()
    logging.info("Access %s for %s", status.lower(), name)


def _split_face_name(name: str) -> Tuple[str, str]:
    first_name, separator, last_name = name.partition("_")
    if not separator or not first_name or not last_name:
        raise ValueError(f"Face image name must use first_last format: {name}")
    return first_name, last_name


def is_access_allowed(session, name: str) -> bool:
    first_name, last_name = _split_face_name(name)
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    course = (
        session.query(Course)
        .filter(
            Course.first_name.ilike(first_name),
            Course.last_name.ilike(last_name),
            Course.course_date == current_date,
            Course.start_time <= current_time,
            Course.end_time >= current_time,
        )
        .first()
    )
    return bool(course)


def load_face_images(upload_folder: Path) -> Tuple[List[np.ndarray], List[str]]:
    if not upload_folder.exists():
        raise RuntimeError(f"Upload directory does not exist: {upload_folder}")

    images: List[np.ndarray] = []
    class_names: List[str] = []

    for image_path in sorted(upload_folder.iterdir()):
        if not image_path.is_file():
            continue
        if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            logging.warning("Skipping unsupported upload file: %s", image_path.name)
            continue

        image = cv2.imread(str(image_path))
        if image is None:
            logging.warning("Skipping unreadable image: %s", image_path.name)
            continue

        images.append(image)
        class_names.append(image_path.stem)

    if not images:
        raise RuntimeError(f"No valid face images found in {upload_folder}")

    logging.info("Loaded %s face image(s)", len(images))
    return images, class_names


def find_encodings(images: Sequence[np.ndarray], class_names: Sequence[str]):
    encodings = []
    for index, image in enumerate(images):
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        face_encodings = face_recognition.face_encodings(rgb_image)
        if not face_encodings:
            logging.warning("No face detected in image %s", class_names[index])
            continue
        encodings.append(face_encodings[0])
    if not encodings:
        raise RuntimeError("No faces could be encoded from uploaded images")
    return encodings


def annotate_frame(frame, face_location, name: str) -> None:
    y1, x2, y2, x1 = [coordinate * 4 for coordinate in face_location]
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.rectangle(frame, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
    cv2.putText(
        frame,
        name,
        (x1 + 6, y2 - 6),
        cv2.FONT_HERSHEY_COMPLEX,
        1,
        (255, 255, 255),
        2,
    )


def process_frame(frame, known_encodings, class_names, session, controller) -> None:
    frame_small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    frame_small_rgb = cv2.cvtColor(frame_small, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(frame_small_rgb)
    face_encodings = face_recognition.face_encodings(frame_small_rgb, face_locations)

    for face_encoding, face_location in zip(face_encodings, face_locations):
        matches = face_recognition.compare_faces(known_encodings, face_encoding)
        if not any(matches):
            send_to_controller(controller, DENY_COMMAND)
            log_access(session, "unknown", "Denied")
            continue

        face_distances = face_recognition.face_distance(known_encodings, face_encoding)
        match_index = int(np.argmin(face_distances))
        if not matches[match_index]:
            send_to_controller(controller, DENY_COMMAND)
            log_access(session, "unknown", "Denied")
            continue

        name = class_names[match_index]
        try:
            allowed = is_access_allowed(session, name)
        except ValueError as exc:
            logging.warning("Invalid face naming convention: %s", exc)
            allowed = False

        if allowed and send_to_controller(controller, GRANT_COMMAND):
            log_access(session, name, "Granted")
        else:
            send_to_controller(controller, DENY_COMMAND)
            log_access(session, name, "Denied")

        annotate_frame(frame, face_location, name)


def run_worker(config: WorkerConfig) -> int:
    configure_logging(config)
    session = create_session(config.database_url)
    controller = open_controller(config)
    capture = cv2.VideoCapture(config.camera_index)

    try:
        if not capture.isOpened():
            raise RuntimeError(f"Camera {config.camera_index} could not be opened")

        images, class_names = load_face_images(config.upload_folder)
        known_encodings = find_encodings(images, class_names)
        logging.info("Starting recognition loop")

        while True:
            captured, frame = capture.read()
            if not captured:
                logging.error("Failed to capture frame from camera")
                return 1

            process_frame(frame, known_encodings, class_names, session, controller)
            cv2.imshow("Face Recognition", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                logging.info("Recognition loop stopped by operator")
                return 0
    finally:
        capture.release()
        cv2.destroyAllWindows()
        session.close()
        if controller is not None and controller.is_open:
            controller.close()
        logging.info("Recognition worker resources released")


def main() -> int:
    try:
        return run_worker(load_config())
    except Exception as exc:
        logging.exception("Recognition worker failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
