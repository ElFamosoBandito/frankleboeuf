#!/usr/bin/env python3
"""
frankleboeuf — Surveillance locale du regard avec popup vidéo automatique.

Raccourcis clavier (fenêtre caméra active) :
  c         Calibrer le centre de l'écran
  g         Calibrer le bord gauche de l'écran
  d         Calibrer le bord droit de l'écran
  b         Calibrer le bas de l'écran / clavier
  r         Réinitialiser la calibration
  q / Esc   Quitter
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
CONFIG_EXAMPLE_PATH = APP_DIR / "config.example.json"
MODEL_PATH = APP_DIR / "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v")

RIGHT_EYE_INDICES = (
    33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246
)
LEFT_EYE_INDICES = (
    362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398
)

EYE_YAW_GAIN_DEG = 44.0
EYE_PITCH_GAIN_DEG = 40.0

SensitivityPreset = Literal["strict", "normal", "relaxed"]
FocusPhase = Literal["idle", "focused", "distracting", "triggered", "returning"]


@dataclass
class RawGazeSample:
    face_detected: bool
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    iris_offset_x: float = 0.0
    iris_offset_y: float = 0.0
    blink_score: float = 0.0


@dataclass
class GazeCalibration:
    yaw_offset_deg: float = 0.0
    pitch_offset_deg: float = 0.0
    iris_offset_x: float = 0.0
    iris_offset_y: float = 0.0
    left_yaw_deg: Optional[float] = None
    right_yaw_deg: Optional[float] = None
    bottom_pitch_deg: Optional[float] = None


@dataclass
class FocusConfig:
    away_delay_ms: int = 1500
    return_delay_ms: int = 600
    sensitivity: SensitivityPreset = "normal"
    head_compensation: bool = True
    allow_keyboard_glance: bool = True


@dataclass
class FocusState:
    phase: FocusPhase = "idle"
    is_popup_open: bool = False
    phase_started_at: Optional[int] = None


SENSITIVITY_THRESHOLDS: dict[str, dict[str, float]] = {
    "strict": {
        "maxWorldYawDeg": 14.0,
        "maxWorldPitchUpDeg": 9.0,
        "maxWorldPitchDownDeg": 17.0,
        "keyboardExtraDownDeg": 6.0,
        "maxExtremeHeadYawDeg": 38.0,
        "maxExtremeHeadPitchUpDeg": 26.0,
        "maxExtremeHeadPitchDownDeg": 38.0,
        "maxStrictHeadYawDeg": 14.0,
        "maxStrictHeadPitchUpDeg": 10.0,
        "maxStrictHeadPitchDownDeg": 18.0,
        "maxIrisX": 0.28,
        "maxIrisUp": 0.22,
        "maxIrisDown": 0.42,
        "maxBlink": 0.70,
    },
    "normal": {
        "maxWorldYawDeg": 19.0,
        "maxWorldPitchUpDeg": 12.0,
        "maxWorldPitchDownDeg": 22.0,
        "keyboardExtraDownDeg": 7.0,
        "maxExtremeHeadYawDeg": 44.0,
        "maxExtremeHeadPitchUpDeg": 30.0,
        "maxExtremeHeadPitchDownDeg": 44.0,
        "maxStrictHeadYawDeg": 19.0,
        "maxStrictHeadPitchUpDeg": 13.0,
        "maxStrictHeadPitchDownDeg": 22.0,
        "maxIrisX": 0.38,
        "maxIrisUp": 0.30,
        "maxIrisDown": 0.52,
        "maxBlink": 0.76,
    },
    "relaxed": {
        "maxWorldYawDeg": 25.0,
        "maxWorldPitchUpDeg": 16.0,
        "maxWorldPitchDownDeg": 28.0,
        "keyboardExtraDownDeg": 9.0,
        "maxExtremeHeadYawDeg": 50.0,
        "maxExtremeHeadPitchUpDeg": 36.0,
        "maxExtremeHeadPitchDownDeg": 50.0,
        "maxStrictHeadYawDeg": 25.0,
        "maxStrictHeadPitchUpDeg": 17.0,
        "maxStrictHeadPitchDownDeg": 28.0,
        "maxIrisX": 0.48,
        "maxIrisUp": 0.40,
        "maxIrisDown": 0.62,
        "maxBlink": 0.82,
    },
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def calibrate_center(
    sample: RawGazeSample, existing: Optional[GazeCalibration] = None
) -> GazeCalibration:
    if not sample.face_detected:
        return GazeCalibration()
    return GazeCalibration(
        yaw_offset_deg=sample.yaw_deg,
        pitch_offset_deg=sample.pitch_deg,
        iris_offset_x=sample.iris_offset_x,
        iris_offset_y=sample.iris_offset_y,
        left_yaw_deg=existing.left_yaw_deg if existing else None,
        right_yaw_deg=existing.right_yaw_deg if existing else None,
        bottom_pitch_deg=existing.bottom_pitch_deg if existing else None,
    )


def calibrate_left_boundary(
    current: GazeCalibration, sample: RawGazeSample
) -> GazeCalibration:
    if not sample.face_detected:
        return current
    world_yaw = (
        (sample.yaw_deg - current.yaw_offset_deg)
        + (sample.iris_offset_x - current.iris_offset_x) * EYE_YAW_GAIN_DEG
    )
    return GazeCalibration(
        yaw_offset_deg=current.yaw_offset_deg,
        pitch_offset_deg=current.pitch_offset_deg,
        iris_offset_x=current.iris_offset_x,
        iris_offset_y=current.iris_offset_y,
        left_yaw_deg=min(-12.0, max(-46.0, world_yaw)),
        right_yaw_deg=current.right_yaw_deg,
        bottom_pitch_deg=current.bottom_pitch_deg,
    )


def calibrate_right_boundary(
    current: GazeCalibration, sample: RawGazeSample
) -> GazeCalibration:
    if not sample.face_detected:
        return current
    world_yaw = (
        (sample.yaw_deg - current.yaw_offset_deg)
        + (sample.iris_offset_x - current.iris_offset_x) * EYE_YAW_GAIN_DEG
    )
    return GazeCalibration(
        yaw_offset_deg=current.yaw_offset_deg,
        pitch_offset_deg=current.pitch_offset_deg,
        iris_offset_x=current.iris_offset_x,
        iris_offset_y=current.iris_offset_y,
        left_yaw_deg=current.left_yaw_deg,
        right_yaw_deg=max(12.0, min(46.0, world_yaw)),
        bottom_pitch_deg=current.bottom_pitch_deg,
    )


def calibrate_bottom_boundary(
    current: GazeCalibration, sample: RawGazeSample
) -> GazeCalibration:
    if not sample.face_detected:
        return current
    world_pitch = (
        (sample.pitch_deg - current.pitch_offset_deg)
        + (sample.iris_offset_y - current.iris_offset_y) * EYE_PITCH_GAIN_DEG
    )
    return GazeCalibration(
        yaw_offset_deg=current.yaw_offset_deg,
        pitch_offset_deg=current.pitch_offset_deg,
        iris_offset_x=current.iris_offset_x,
        iris_offset_y=current.iris_offset_y,
        left_yaw_deg=current.left_yaw_deg,
        right_yaw_deg=current.right_yaw_deg,
        bottom_pitch_deg=min(-14.0, max(-52.0, world_pitch)),
    )


def extract_sample_from_mediapipe(
    landmarks: Optional[Sequence[Any]],
    blendshapes: Optional[Sequence[Any]],
) -> RawGazeSample:
    if not landmarks or len(landmarks) < 468:
        return RawGazeSample(face_detected=False)

    nose = landmarks[1]
    rc, lc = landmarks[234], landmarks[454]
    fh, ch = landmarks[10], landmarks[152]

    cheek_dx = lc.x - rc.x
    cheek_dy = lc.y - rc.y
    cheek_span = max(0.04, math.hypot(cheek_dx, cheek_dy))
    depth_yaw_deg = math.degrees(math.atan2(rc.z - lc.z, cheek_span))

    mid_cheek_x = (rc.x + lc.x) * 0.5
    mid_cheek_y = (rc.y + lc.y) * 0.5
    ux, uy = cheek_dx / cheek_span, cheek_dy / cheek_span
    nose_along_cheek = (
        (nose.x - mid_cheek_x) * ux + (nose.y - mid_cheek_y) * uy
    ) / (cheek_span * 0.5)
    nose_yaw_deg = math.degrees(math.asin(_clamp(-nose_along_cheek, -0.95, 0.95)))
    yaw_deg = (
        depth_yaw_deg * 0.65 + nose_yaw_deg * 0.35
        if abs(rc.z - lc.z) > 0.0005
        else nose_yaw_deg
    )

    face_dx = ch.x - fh.x
    face_dy = ch.y - fh.y
    face_height = max(0.04, math.hypot(face_dx, face_dy))
    depth_pitch_deg = math.degrees(math.atan2(fh.z - ch.z, face_height))

    mid_vert_x = (fh.x + ch.x) * 0.5
    mid_vert_y = (fh.y + ch.y) * 0.5
    vx, vy = face_dx / face_height, face_dy / face_height
    nose_along_vert = (
        (nose.x - mid_vert_x) * vx + (nose.y - mid_vert_y) * vy
    ) / (face_height * 0.5)
    nose_pitch_deg = _clamp(-(nose_along_vert - 0.06) * 65.0, -45.0, 45.0)
    pitch_deg = (
        depth_pitch_deg * 0.7 + nose_pitch_deg * 0.3
        if abs(fh.z - ch.z) > 0.0005
        else nose_pitch_deg
    )

    bs = {c.category_name: float(c.score) for c in (blendshapes or ())}
    blink_score = (bs.get("eyeBlinkLeft", 0.0) + bs.get("eyeBlinkRight", 0.0)) * 0.5

    blend_look_left = (bs.get("eyeLookOutLeft", 0.0) + bs.get("eyeLookInRight", 0.0)) * 0.5
    blend_look_right = (bs.get("eyeLookInLeft", 0.0) + bs.get("eyeLookOutRight", 0.0)) * 0.5
    blend_iris_x = _clamp((blend_look_right - blend_look_left) * 1.15, -1.0, 1.0)

    blend_look_up = (bs.get("eyeLookUpLeft", 0.0) + bs.get("eyeLookUpRight", 0.0)) * 0.5
    blend_look_down = (bs.get("eyeLookDownLeft", 0.0) + bs.get("eyeLookDownRight", 0.0)) * 0.5
    blend_iris_y = _clamp(blend_look_up * 2.1 - blend_look_down * 1.35, -1.0, 1.0)

    geo_iris_x = 0.0
    geo_iris_y = 0.0
    has_geo_iris = False

    if len(landmarks) >= 478:
        def project_eye(start_lm: Any, end_lm: Any, iris_lm: Any) -> tuple[float, float]:
            ex = end_lm.x - start_lm.x
            ey = end_lm.y - start_lm.y
            eye_width = max(0.005, math.hypot(ex, ey))
            eux, euy = ex / eye_width, ey / eye_width
            evx, evy = -euy, eux
            dx = iris_lm.x - (start_lm.x + end_lm.x) * 0.5
            dy = iris_lm.y - (start_lm.y + end_lm.y) * 0.5
            horiz = (dx * eux + dy * euy) / (eye_width * 0.5)
            vert = (dx * evx + dy * evy) / eye_width
            return horiz, vert

        r_h, r_v = project_eye(landmarks[33], landmarks[133], landmarks[468])
        l_h, l_v = project_eye(landmarks[362], landmarks[263], landmarks[473])
        geo_iris_x = _clamp(-((r_h + l_h) * 0.5) * 1.65, -1.0, 1.0)
        geo_iris_y = _clamp((-((r_v + l_v) * 0.5) - 0.025) * 5.2, -1.0, 1.0)
        has_geo_iris = True

    if bs:
        iris_offset_x = blend_iris_x * 0.62 + geo_iris_x * 0.38 if has_geo_iris else blend_iris_x
        iris_offset_y = blend_iris_y * 0.60 + geo_iris_y * 0.40 if has_geo_iris else blend_iris_y
    else:
        iris_offset_x = geo_iris_x
        iris_offset_y = geo_iris_y

    return RawGazeSample(
        face_detected=True,
        yaw_deg=yaw_deg,
        pitch_deg=pitch_deg,
        iris_offset_x=iris_offset_x,
        iris_offset_y=iris_offset_y,
        blink_score=blink_score,
    )


def is_looking_at_screen(
    sample: RawGazeSample,
    calibration: GazeCalibration,
    config: FocusConfig,
) -> bool:
    if not sample.face_detected:
        return False

    t = SENSITIVITY_THRESHOLDS.get(config.sensitivity, SENSITIVITY_THRESHOLDS["normal"])

    rel_yaw = sample.yaw_deg - calibration.yaw_offset_deg
    rel_pitch = sample.pitch_deg - calibration.pitch_offset_deg
    rel_iris_x = sample.iris_offset_x - calibration.iris_offset_x
    rel_iris_y = sample.iris_offset_y - calibration.iris_offset_y

    world_yaw = rel_yaw + rel_iris_x * EYE_YAW_GAIN_DEG
    world_pitch = rel_pitch + rel_iris_y * EYE_PITCH_GAIN_DEG

    max_left_yaw = (
        max(t["maxWorldYawDeg"], abs(calibration.left_yaw_deg) + 4.0)
        if calibration.left_yaw_deg is not None
        else t["maxWorldYawDeg"]
    )
    max_right_yaw = (
        max(t["maxWorldYawDeg"], abs(calibration.right_yaw_deg) + 4.0)
        if calibration.right_yaw_deg is not None
        else t["maxWorldYawDeg"]
    )

    max_down = t["maxWorldPitchDownDeg"] + (
        t["keyboardExtraDownDeg"] if config.allow_keyboard_glance else 0.0
    )
    if calibration.bottom_pitch_deg is not None:
        max_down = max(max_down, abs(calibration.bottom_pitch_deg) + 4.0)

    downward_deg = max(0.0, -world_pitch, -rel_pitch)
    eyelid_bonus = min(0.16, (downward_deg - 8.0) * 0.0065) if downward_deg > 8.0 else 0.0
    if sample.blink_score >= min(0.94, t["maxBlink"] + eyelid_bonus):
        return False

    if config.head_compensation:
        horiz_limit = max_left_yaw if world_yaw < 0.0 else max_right_yaw
        world_yaw_ratio = abs(world_yaw) / horiz_limit
        world_pitch_ratio = (
            world_pitch / t["maxWorldPitchUpDeg"]
            if world_pitch >= 0.0
            else abs(world_pitch) / max_down
        )

        extreme_head_yaw = max(t["maxExtremeHeadYawDeg"], horiz_limit + 12.0)
        extreme_head_pitch = (
            t["maxExtremeHeadPitchUpDeg"]
            if rel_pitch >= 0.0
            else max(t["maxExtremeHeadPitchDownDeg"], max_down + 8.0)
        )

        if abs(rel_yaw) >= extreme_head_yaw or abs(rel_pitch) >= extreme_head_pitch:
            return False
        return world_yaw_ratio < 1.0 and world_pitch_ratio < 1.0

    strict_down = t["maxStrictHeadPitchDownDeg"] + (
        t["keyboardExtraDownDeg"] if config.allow_keyboard_glance else 0.0
    )
    yaw_ratio = abs(rel_yaw) / t["maxStrictHeadYawDeg"]
    pitch_ratio = (
        rel_pitch / t["maxStrictHeadPitchUpDeg"]
        if rel_pitch >= 0.0
        else abs(rel_pitch) / strict_down
    )
    iris_x_ratio = abs(rel_iris_x) / t["maxIrisX"]
    iris_y_limit = (
        t["maxIrisUp"]
        if rel_iris_y >= 0.0
        else t["maxIrisDown"] + (0.14 if config.allow_keyboard_glance else 0.0)
    )
    iris_y_ratio = abs(rel_iris_y) / iris_y_limit

    return max(yaw_ratio, iris_x_ratio, pitch_ratio, iris_y_ratio) < 1.0


def step_focus_state(
    state: FocusState,
    looking_at_screen: bool,
    now_ms: int,
    config: FocusConfig,
) -> FocusState:
    away_delay = max(100, config.away_delay_ms)
    return_delay = max(0, config.return_delay_ms)

    phase = state.phase
    is_popup_open = state.is_popup_open
    phase_started_at = state.phase_started_at

    if phase == "idle":
        phase = "focused" if looking_at_screen else "distracting"
        phase_started_at = now_ms
    elif phase == "focused":
        if not looking_at_screen:
            phase = "distracting"
            phase_started_at = now_ms
    elif phase == "distracting":
        if looking_at_screen:
            phase = "focused"
            phase_started_at = now_ms
        elif now_ms - (phase_started_at or now_ms) >= away_delay:
            phase = "triggered"
            is_popup_open = True
    elif phase == "triggered":
        if looking_at_screen:
            if return_delay == 0:
                phase = "focused"
                is_popup_open = False
                phase_started_at = now_ms
            else:
                phase = "returning"
                phase_started_at = now_ms
    elif phase == "returning":
        if not looking_at_screen:
            phase = "triggered"
            is_popup_open = True
        elif now_ms - (phase_started_at or now_ms) >= return_delay:
            phase = "focused"
            is_popup_open = False
            phase_started_at = now_ms

    return FocusState(
        phase=phase,
        is_popup_open=is_popup_open,
        phase_started_at=phase_started_at,
    )


def load_config() -> tuple[FocusConfig, GazeCalibration, dict[str, Any]]:
    raw: dict[str, Any] = {}
    config_path = CONFIG_PATH if CONFIG_PATH.exists() else CONFIG_EXAMPLE_PATH
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}

    sensitivity = raw.get("sensitivity", "normal")
    if sensitivity not in ("strict", "normal", "relaxed"):
        sensitivity = "normal"

    config = FocusConfig(
        away_delay_ms=int(raw.get("awayDelayMs", 1500)),
        return_delay_ms=int(raw.get("returnDelayMs", 600)),
        sensitivity=sensitivity,
        head_compensation=bool(raw.get("headCompensation", True)),
        allow_keyboard_glance=bool(raw.get("allowKeyboardGlance", True)),
    )

    cal = raw.get("calibration") or {}
    calibration = GazeCalibration(
        yaw_offset_deg=float(cal.get("yawOffsetDeg", 0.0)),
        pitch_offset_deg=float(cal.get("pitchOffsetDeg", 0.0)),
        iris_offset_x=float(cal.get("irisOffsetX", 0.0)),
        iris_offset_y=float(cal.get("irisOffsetY", 0.0)),
        left_yaw_deg=float(cal["leftYawDeg"]) if cal.get("leftYawDeg") is not None else None,
        right_yaw_deg=float(cal["rightYawDeg"]) if cal.get("rightYawDeg") is not None else None,
        bottom_pitch_deg=(
            float(cal["bottomPitchDeg"]) if cal.get("bottomPitchDeg") is not None else None
        ),
    )

    return config, calibration, raw


def save_raw_config(raw: dict[str, Any]) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception:
        pass


def save_calibration(raw: dict[str, Any], calibration: GazeCalibration) -> None:
    raw["calibration"] = {
        "yawOffsetDeg": round(calibration.yaw_offset_deg, 3),
        "pitchOffsetDeg": round(calibration.pitch_offset_deg, 3),
        "irisOffsetX": round(calibration.iris_offset_x, 4),
        "irisOffsetY": round(calibration.iris_offset_y, 4),
        "leftYawDeg": round(calibration.left_yaw_deg, 3) if calibration.left_yaw_deg is not None else None,
        "rightYawDeg": round(calibration.right_yaw_deg, 3) if calibration.right_yaw_deg is not None else None,
        "bottomPitchDeg": (
            round(calibration.bottom_pitch_deg, 3)
            if calibration.bottom_pitch_deg is not None
            else None
        ),
    }
    save_raw_config(raw)


def resolve_video_source(raw: dict[str, Any]) -> tuple[Optional[Path], Optional[str]]:
    video_dir = APP_DIR / "video"
    video_dir.mkdir(exist_ok=True)

    video_file = raw.get("videoFile")
    if isinstance(video_file, str) and video_file.strip():
        candidate = (APP_DIR / video_file).resolve()
        if candidate.is_file():
            return candidate, None

    for path in sorted(video_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            return path.resolve(), None

    for path in sorted(APP_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            return path.resolve(), None

    video_url = raw.get("videoUrl")
    if isinstance(video_url, str) and video_url.startswith(("http://", "https://")):
        return None, video_url

    return None, None


def ensure_model_file() -> Path:
    if MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 1_000_000:
        return MODEL_PATH
    print("Téléchargement du modèle MediaPipe FaceLandmarker...")
    tmp = MODEL_PATH.with_suffix(".task.tmp")
    urllib.request.urlretrieve(MODEL_URL, tmp)
    tmp.replace(MODEL_PATH)
    return MODEL_PATH


def run_app() -> int:
    import cv2
    import mediapipe as mp
    import numpy as np
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QImage, QKeyEvent, QPixmap
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    config, calibration, raw_config = load_config()
    video_path, video_url = resolve_video_source(raw_config)
    camera_index = int(raw_config.get("cameraIndex", 0))
    model_path = ensure_model_file()

    landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(
        mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
        )
    )

    app = QApplication(sys.argv)
    app.setApplicationName("frankleboeuf")

    class VideoPopup(QWidget):
        def __init__(
            self,
            local_file: Optional[Path],
            remote_url: Optional[str],
            cfg_store: dict[str, Any],
        ) -> None:
            super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowTitle("frankleboeuf")
            self.setStyleSheet("background-color: #000000;")

            self._cfg_store = cfg_store
            self._is_positioning = True
            self._saved_pos: Optional[tuple[int, int]] = None

            saved_geo = cfg_store.get("popupGeometry")
            init_w, init_h = 480, 270
            if isinstance(saved_geo, dict):
                w_val = saved_geo.get("width")
                h_val = saved_geo.get("height")
                x_val = saved_geo.get("x")
                y_val = saved_geo.get("y")
                if isinstance(w_val, (int, float)) and isinstance(h_val, (int, float)):
                    init_w = max(240, int(w_val))
                    init_h = max(140, int(h_val))
                if isinstance(x_val, (int, float)) and isinstance(y_val, (int, float)):
                    self._saved_pos = (int(x_val), int(y_val))

            self.resize(init_w, init_h)
            self._is_positioning = False

            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._flush_geometry)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.player: Optional[QMediaPlayer] = None
            self.audio_output: Optional[QAudioOutput] = None
            self.on_manual_close = None

            if local_file is not None or remote_url is not None:
                video_widget = QVideoWidget(self)
                layout.addWidget(video_widget)

                self.audio_output = QAudioOutput(self)
                self.audio_output.setVolume(1.0)

                self.player = QMediaPlayer(self)
                self.player.setAudioOutput(self.audio_output)
                self.player.setVideoOutput(video_widget)
                self.player.setLoops(QMediaPlayer.Loops.Infinite)
                self.player.setSource(
                    QUrl.fromLocalFile(str(local_file))
                    if local_file is not None
                    else QUrl(remote_url or "")
                )
            else:
                label = QLabel(
                    "Aucune vidéo trouvée.\nPlacez votre fichier .mp4 dans le dossier « video ».",
                    self,
                )
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("color: #F1F5F9; font-size: 16px; padding: 24px;")
                layout.addWidget(label)

        def _is_position_visible(self, x: int, y: int) -> bool:
            cx = x + self.width() // 2
            cy = y + self.height() // 2
            for screen in QApplication.screens():
                if screen.availableGeometry().contains(cx, cy):
                    return True
            return False

        def _flush_geometry(self) -> None:
            if self._saved_pos is None:
                return
            self._cfg_store["popupGeometry"] = {
                "x": self._saved_pos[0],
                "y": self._saved_pos[1],
                "width": self.width(),
                "height": self.height(),
            }
            save_raw_config(self._cfg_store)

        def _record_user_geometry(self) -> None:
            if self._is_positioning or not self.isVisible():
                return
            self._saved_pos = (self.x(), self.y())
            self._save_timer.start(250)

        def moveEvent(self, event: Any) -> None:
            super().moveEvent(event)
            self._record_user_geometry()

        def resizeEvent(self, event: Any) -> None:
            super().resizeEvent(event)
            self._record_user_geometry()

        def show_and_play(self) -> None:
            self._is_positioning = True
            if self._saved_pos is not None and self._is_position_visible(*self._saved_pos):
                self.move(self._saved_pos[0], self._saved_pos[1])
            else:
                screen = QApplication.primaryScreen()
                if screen is not None:
                    geo = screen.availableGeometry()
                    margin = 24
                    pos_x = max(geo.x(), geo.x() + geo.width() - self.width() - margin)
                    pos_y = max(geo.y(), geo.y() + geo.height() - self.height() - margin)
                    self.move(pos_x, pos_y)
                    self._saved_pos = (pos_x, pos_y)

            if self.player is not None:
                self.player.setPosition(0)
                self.player.play()
            self.show()
            self.raise_()
            self._is_positioning = False

        def stop_and_hide(self) -> None:
            if self._save_timer.isActive():
                self._save_timer.stop()
                self._flush_geometry()
            if self.player is not None:
                self.player.pause()
                self.player.setPosition(0)
            if self.isVisible():
                self.hide()

        def closeEvent(self, event: Any) -> None:
            self.stop_and_hide()
            if callable(self.on_manual_close):
                self.on_manual_close()
            event.ignore()

    def draw_eyes(frame_bgr: np.ndarray, landmarks: Sequence[Any], focused: bool) -> None:
        h, w = frame_bgr.shape[:2]
        iris_color = (74, 163, 22) if focused else (77, 72, 229)
        contour_color = (60, 128, 20) if focused else (62, 58, 175)

        for indices in (RIGHT_EYE_INDICES, LEFT_EYE_INDICES):
            pts = np.array(
                [
                    [int(round(landmarks[idx].x * w)), int(round(landmarks[idx].y * h))]
                    for idx in indices
                ],
                dtype=np.int32,
            )
            cv2.polylines(
                frame_bgr, [pts], True, contour_color, 1, lineType=cv2.LINE_AA
            )

        if len(landmarks) >= 478:
            eye_w = math.hypot(
                (landmarks[133].x - landmarks[33].x) * w,
                (landmarks[133].y - landmarks[33].y) * h,
            )
            radius = int(max(4, min(11, round(eye_w * 0.22))))
            for idx in (468, 473):
                cx = int(round(landmarks[idx].x * w))
                cy = int(round(landmarks[idx].y * h))
                cv2.circle(frame_bgr, (cx, cy), radius, iris_color, 2, lineType=cv2.LINE_AA)
                cv2.circle(frame_bgr, (cx, cy), 2, iris_color, -1, lineType=cv2.LINE_AA)

    class CameraWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("frankleboeuf")
            self.setStyleSheet("background-color: #0B0E14;")
            self.resize(640, 360)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.feed_label = QLabel(self)
            self.feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feed_label.setMinimumSize(320, 180)
            layout.addWidget(self.feed_label)

            self.status_label = QLabel(self)
            self.status_label.setTextFormat(Qt.TextFormat.RichText)
            self.status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.status_label.setStyleSheet(
                "background-color: rgba(11, 14, 20, 175);"
                "color: #F8FAFC;"
                "font-size: 13px;"
                "font-weight: 600;"
                "padding: 5px 10px;"
                "border-radius: 6px;"
            )
            self.status_label.move(12, 12)
            self.status_label.hide()

            self.config = config
            self.calibration = calibration
            self.raw_config = raw_config
            self.state = FocusState()
            self.latest_sample: Optional[RawGazeSample] = None
            self.prev_focused: Optional[bool] = None
            self.prev_popup_open = False
            self.last_ts_ms = 0

            self.popup = VideoPopup(video_path, video_url, self.raw_config)
            self.popup.on_manual_close = self._on_popup_closed

            self.cap = cv2.VideoCapture(camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            self.cap.set(cv2.CAP_PROP_FPS, 24)

            if not self.cap.isOpened():
                self.feed_label.setText("Impossible d'ouvrir la webcam.")
                self.feed_label.setStyleSheet("color: #F1F5F9; font-size: 15px;")
                return

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.timer.start(45)

        def _update_status_label(self, focused: bool) -> None:
            if self.prev_focused is focused:
                return
            self.prev_focused = focused
            if focused:
                self.status_label.setText('<span style="color:#22C55E;">●</span>&nbsp; Focus')
            else:
                self.status_label.setText('<span style="color:#EF4444;">●</span>&nbsp; Hors écran')
            self.status_label.adjustSize()
            self.status_label.show()
            self.status_label.raise_()

        def _on_popup_closed(self) -> None:
            self.state = FocusState(
                phase="focused",
                is_popup_open=False,
                phase_started_at=int(time.time() * 1000),
            )
            self.prev_popup_open = False

        def _tick(self) -> None:
            ok, frame_bgr = self.cap.read()
            if not ok or frame_bgr is None:
                return

            ts_ms = int(time.monotonic() * 1000)
            if ts_ms <= self.last_ts_ms:
                ts_ms = self.last_ts_ms + 1
            self.last_ts_ms = ts_ms

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            result = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb), ts_ms
            )

            landmarks = result.face_landmarks[0] if result.face_landmarks else None
            blendshapes = result.face_blendshapes[0] if result.face_blendshapes else None

            sample = extract_sample_from_mediapipe(landmarks, blendshapes)
            self.latest_sample = sample

            focused = is_looking_at_screen(sample, self.calibration, self.config)
            self.state = step_focus_state(
                self.state, focused, int(time.time() * 1000), self.config
            )

            if landmarks:
                draw_eyes(frame_bgr, landmarks, focused)

            mirrored_rgb = cv2.cvtColor(cv2.flip(frame_bgr, 1), cv2.COLOR_BGR2RGB)
            h, w, ch = mirrored_rgb.shape
            qimg = QImage(mirrored_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            self.feed_label.setPixmap(
                QPixmap.fromImage(qimg).scaled(
                    self.feed_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._update_status_label(focused)

            if self.state.is_popup_open and not self.prev_popup_open:
                self.popup.show_and_play()
            elif not self.state.is_popup_open and self.prev_popup_open:
                self.popup.stop_and_hide()
            self.prev_popup_open = self.state.is_popup_open

        def keyPressEvent(self, event: QKeyEvent) -> None:
            key = event.key()
            if key in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
                self.close()
                return
            if self.latest_sample and self.latest_sample.face_detected:
                if key == Qt.Key.Key_C:
                    self.calibration = calibrate_center(self.latest_sample, self.calibration)
                    save_calibration(self.raw_config, self.calibration)
                elif key == Qt.Key.Key_G:
                    self.calibration = calibrate_left_boundary(
                        self.calibration, self.latest_sample
                    )
                    save_calibration(self.raw_config, self.calibration)
                elif key == Qt.Key.Key_D:
                    self.calibration = calibrate_right_boundary(
                        self.calibration, self.latest_sample
                    )
                    save_calibration(self.raw_config, self.calibration)
                elif key == Qt.Key.Key_B:
                    self.calibration = calibrate_bottom_boundary(
                        self.calibration, self.latest_sample
                    )
                    save_calibration(self.raw_config, self.calibration)
            if key == Qt.Key.Key_R:
                self.calibration = GazeCalibration()
                save_calibration(self.raw_config, self.calibration)

        def closeEvent(self, event: Any) -> None:
            if hasattr(self, "timer") and self.timer.isActive():
                self.timer.stop()
            if hasattr(self, "cap") and self.cap.isOpened():
                self.cap.release()
            self.popup.stop_and_hide()
            self.popup.deleteLater()
            landmarker.close()
            event.accept()
            QApplication.quit()

    window = CameraWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
