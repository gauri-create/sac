"""
face_engine/encoding.py
Build and persist face encodings from a dataset of known faces.
"""

import os
import pickle
import logging
from pathlib import Path
from typing import List, Tuple

import face_recognition
import numpy as np

logger = logging.getLogger(__name__)

# Default paths (relative to project root — overridden by absolute paths in app factory)
ENCODINGS_PATH   = Path("models/encodings.pkl")
KNOWN_FACES_DIR  = Path("data/known_faces")


class EncodingManager:
    """
    Manages the encoding database: build from images, persist, load.

    Dataset layout expected:
        data/known_faces/
            Alice_Smith/
                photo1.jpg
                photo2.png
    Each subdirectory name becomes the person's display name (underscores→spaces).
    """

    def __init__(
        self,
        known_faces_dir: Path = KNOWN_FACES_DIR,
        encodings_path: Path = ENCODINGS_PATH,
    ):
        self.known_faces_dir = Path(known_faces_dir)
        self.encodings_path  = Path(encodings_path)
        self.known_encodings: List[np.ndarray] = []
        self.known_names: List[str] = []

    def build_encodings(self, force_rebuild: bool = False) -> int:
        """
        Scan known_faces_dir and build encodings.
        If encodings_path already exists and force_rebuild=False, load from cache.

        Returns number of unique identities encoded.
        """
        if self.encodings_path.exists() and not force_rebuild:
            logger.info("Encodings file exists — loading from cache.")
            self.load_encodings()
            return len(set(self.known_names))

        logger.info("Building encodings from %s …", self.known_faces_dir)
        self.known_encodings = []
        self.known_names     = []

        if not self.known_faces_dir.exists():
            self.known_faces_dir.mkdir(parents=True, exist_ok=True)
            logger.warning("Created empty known_faces directory. Add images and rebuild.")
            return 0

        # Support BOTH flat images in the root AND images inside per-person subdirs
        for item in sorted(self.known_faces_dir.iterdir()):
            if item.is_dir():
                # Per-person subdirectory: dir name = person name
                name = item.name.replace("_", " ")
                image_files = [
                    f for f in item.iterdir()
                    if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
                ]
                if not image_files:
                    logger.warning("No images found for %s — skipping.", name)
                    continue
                for img_path in image_files:
                    encodings = self._encode_image(img_path)
                    if encodings:
                        self.known_encodings.extend(encodings)
                        self.known_names.extend([name] * len(encodings))
                        logger.debug("  + %s: %d encoding(s) from %s", name, len(encodings), img_path.name)
            elif item.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
                # Flat image in root dir: use stem as name
                name = item.stem.replace("_", " ")
                encodings = self._encode_image(item)
                if encodings:
                    self.known_encodings.extend(encodings)
                    self.known_names.extend([name] * len(encodings))
                    logger.debug("  + %s: %d encoding(s) from %s", name, len(encodings), item.name)

        if self.known_encodings:
            self._save_encodings()
        else:
            logger.warning("No face encodings found. Check known_faces directory.")

        logger.info(
            "Encoding complete. %d faces / %d identities.",
            len(self.known_encodings),
            len(set(self.known_names)) if self.known_names else 0,
        )
        return len(set(self.known_names)) if self.known_names else 0

    def load_encodings(self):
        """Load pre-built encodings from disk."""
        if not self.encodings_path.exists():
            raise FileNotFoundError(
                f"Encodings file not found at {self.encodings_path}. "
                "Run build_encodings() first."
            )
        with open(self.encodings_path, "rb") as f:
            data = pickle.load(f)
        self.known_encodings = data["encodings"]
        self.known_names     = data["names"]
        logger.info(
            "Loaded %d encodings for %d identities.",
            len(self.known_encodings),
            len(set(self.known_names)),
        )

    def add_person(self, name: str, image_paths: List[str]) -> int:
        """
        Incrementally add a new person without full rebuild.
        Returns number of encodings successfully added.
        """
        added = 0
        safe_name  = name.replace(" ", "_")
        person_dir = self.known_faces_dir / safe_name
        person_dir.mkdir(parents=True, exist_ok=True)

        for img_path in image_paths:
            encodings = self._encode_image(Path(img_path))
            if encodings:
                self.known_encodings.extend(encodings)
                self.known_names.extend([name] * len(encodings))
                added += len(encodings)

        if added:
            self._save_encodings()
            logger.info("Added %d encoding(s) for '%s'.", added, name)
        return added

    def get_data(self) -> Tuple[List[np.ndarray], List[str]]:
        """Return (encodings_list, names_list) for use by the recognizer."""
        return self.known_encodings, self.known_names

    def _encode_image(self, img_path: Path) -> List[np.ndarray]:
        """Return list of 128-d face encodings found in the image."""
        try:
            img = face_recognition.load_image_file(str(img_path))
            locations = face_recognition.face_locations(img, model="hog")
            if not locations:
                logger.warning("No face found in %s", img_path)
                return []
            encodings = face_recognition.face_encodings(img, locations)
            return list(encodings)
        except Exception as exc:
            logger.error("Failed to encode %s: %s", img_path, exc)
            return []

    def _save_encodings(self):
        self.encodings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.encodings_path, "wb") as f:
            pickle.dump(
                {"encodings": self.known_encodings, "names": self.known_names}, f
            )
        logger.info("Encodings saved to %s.", self.encodings_path)
